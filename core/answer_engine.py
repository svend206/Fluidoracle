from __future__ import annotations
"""
Fluidoracle — Answer Engine
============================
Core intelligence: retrieves RAG context and generates expert answers via Claude.

Vertical-agnostic: receives system prompt and retrieval config from VerticalConfig.

Flow:
  1. Call verified_query() from the retrieval pipeline (vertical-scoped)
  2. Build a prompt with system instructions + retrieved context
  3. Call Claude API for answer generation
  4. Return structured result (with automatic retry on refusal)
"""

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

import anthropic
from dotenv import load_dotenv

# Load env from project root
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "claude-sonnet-4-20250514")
STREAM_MODEL = os.getenv("STREAM_MODEL", "claude-sonnet-4-5-20250929")

print(f"[answer_engine] Using model: {CLAUDE_MODEL}, fallback: {FALLBACK_MODEL}, stream: {STREAM_MODEL}")

# Import retrieval from the core package (no more sys.path hacks)
from core.database import log_llm_usage_sync
from core.retrieval.verified_query import verified_query

# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------
_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file."
            )
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# System prompt — loaded from vertical config
# ---------------------------------------------------------------------------
# Legacy module-level SYSTEM_PROMPT maintained for backward compatibility.
# New code should use get_system_prompt(vertical_config) instead.
SYSTEM_PROMPT: str = ""  # Will be set by init_vertical() or load at first use

def get_system_prompt(vertical_config=None) -> str:
    """Get the answering system prompt for a vertical.

    If vertical_config is provided, returns that vertical's answering_prompt.
    Otherwise falls back to the module-level SYSTEM_PROMPT (set by init_vertical).
    """
    if vertical_config is not None:
        return vertical_config.answering_prompt
    if SYSTEM_PROMPT:
        return SYSTEM_PROMPT
    # Fallback: try to load default vertical
    try:
        from core.vertical_loader import get_vertical_config
        vc = get_vertical_config("fps", "hydraulic_filtration")
        return vc.answering_prompt
    except Exception:
        raise RuntimeError(
            "No vertical configured. Call init_vertical() or pass vertical_config."
        )


def init_vertical(vertical_config) -> None:
    """Initialize the module-level SYSTEM_PROMPT from a vertical config.

    Called at application startup to set the default vertical for this module.
    """
    global SYSTEM_PROMPT
    SYSTEM_PROMPT = vertical_config.answering_prompt


# Legacy SYSTEM_PROMPT removed — now loaded from vertical config files.
# See platforms/<platform>/verticals/<vertical>/answering_prompt.md


# Addendum appended to the system prompt when RAG confidence is LOW.
# This tells Claude to answer from its training knowledge rather than
# constraining itself to the (irrelevant) retrieved chunks.
LOW_CONFIDENCE_ADDENDUM = """

IMPORTANT — LOW RETRIEVAL CONFIDENCE:
The knowledge base did not return relevant results for this question.
DO NOT refuse to answer or say you cannot help. Instead, answer the question fully using:
1. Your training data and domain expertise relevant to this vertical's subject matter.
2. The CORE REFERENCE DATA provided above (tables, equations, rules of thumb from your system prompt).
3. Standard references and authoritative publications in this domain.

Tag all claims as [Domain knowledge] or [Standard reference: Standard/Author, Year].
State upfront that the answer draws on general domain knowledge rather than the curated knowledge base, then give a thorough, quantitative answer."""


# ===========================================================================
# Answer Generation
# ===========================================================================

def generate_answer(question: str) -> dict:
    """Generate an expert answer using RAG retrieval + Claude.

    Returns:
        {
            "answer": str,
            "confidence": str,        # HIGH, MEDIUM, LOW
            "sources": list[str],     # citation strings
            "warnings": list[str],    # verification warnings
            "rag_results": dict,      # full RAG output for logging
        }
    """
    # Step 1: Retrieve context via verified query
    t_start = time.time()
    try:
        rag_result = verified_query(question, top_k=12, use_reranker=True)
    except Exception as e:
        # If RAG fails (e.g., empty vector store), proceed without context
        rag_result = {
            "query": question,
            "results": [],
            "confidence": {
                "level": "LOW",
                "top_score": 0.0,
                "num_results": 0,
                "num_high_confidence": 0,
                "num_sources": 0,
                "sources": [],
                "contradictions": [],
                "reasoning": f"RAG retrieval failed: {e}",
            },
            "citations": [],
            "warnings": [f"Knowledge base retrieval failed: {e}. Answer based on general knowledge only."],
            "gap_logged": False,
        }

    # Step 2: Build context parts from retrieved chunks
    all_chunks = []
    for i, result in enumerate(rag_result["results"], 1):
        source = result.get("source", "unknown")
        score = result.get("rerank_score", 0.0)
        text = result.get("parent_text", "")
        all_chunks.append({
            "index": i,
            "source": source,
            "score": score,
            "text": text,
        })

    t_rag = time.time()

    confidence_level = rag_result["confidence"]["level"]
    confidence_reasoning = rag_result["confidence"]["reasoning"]

    # When confidence is LOW, drop irrelevant chunks (they add noise and
    # can cause Claude to fixate on unrelated content) and append an
    # instruction telling Claude to answer from its general knowledge.
    system_prompt = get_system_prompt()
    if confidence_level == "LOW":
        all_chunks = []  # discard noisy low-relevance chunks
        system_prompt = get_system_prompt() + LOW_CONFIDENCE_ADDENDUM

    # Step 3: Call Claude with automatic model fallback on refusal.
    #
    # Some questions trigger safety refusals in newer models (Opus 4.6, Sonnet 4.5)
    # but work fine in older models (Sonnet 4). Strategy:
    #   1. Try primary model with all RAG chunks
    #   2. Try primary model with no RAG chunks (copyright in chunks may cause refusal)
    #   3. Try fallback model with all RAG chunks
    #   4. Try fallback model with no RAG chunks
    client = _get_client()
    answer_text = None

    def _build_user_message(chunks):
        if chunks:
            context_parts = []
            for c in chunks:
                context_parts.append(
                    f"--- Reference [{c['index']}]: {c['source']} "
                    f"(relevance: {c['score']:.3f}) ---\n{c['text']}"
                )
            context_block = "\n\n".join(context_parts)

            # Build deduplicated source summary so Claude sees the big picture
            from collections import Counter
            source_counts = Counter(c["source"] for c in chunks)
            source_lines = [
                f"  {i}. {src} — {cnt} chunk{'s' if cnt > 1 else ''}"
                for i, (src, cnt) in enumerate(source_counts.items(), 1)
            ]
            source_summary = "\n".join(source_lines)
        else:
            context_block = (
                "(No relevant documents found in the knowledge base. "
                "Answer using your expert knowledge and the reference "
                "data in your system instructions.)"
            )
            source_summary = "  (none)"

        return f"""RETRIEVAL CONFIDENCE: {confidence_level}
{confidence_reasoning}

UNIQUE SOURCES RETRIEVED:
{source_summary}

RETRIEVED CONTEXT (internal engineering reference notes):
{context_block}

QUESTION:
{question}"""

    # Define retry strategies: (label, model, chunks)
    strategies = [
        ("primary+context", CLAUDE_MODEL, list(all_chunks)),
        ("primary+no_context", CLAUDE_MODEL, []),
        ("fallback+context", FALLBACK_MODEL, list(all_chunks)),
        ("fallback+no_context", FALLBACK_MODEL, []),
    ]

    for strategy_name, model, chunks_to_use in strategies:
        user_message = _build_user_message(chunks_to_use)

        try:
            response = client.messages.create(
                model=model,
                max_tokens=4000,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_message},
                ],
            )
        except Exception as e:
            logger.error(f"[{strategy_name}] API error with {model}: {e}")
            continue

        logger.info(
            f"[{strategy_name}] model={response.model} "
            f"stop_reason={response.stop_reason} "
            f"input_tokens={response.usage.input_tokens} "
            f"output_tokens={response.usage.output_tokens} "
            f"chunks={len(chunks_to_use)}"
        )
        log_llm_usage_sync(response.usage, response.model, "answering")

        # Check if we got a valid response
        if response.content and len(response.content) > 0:
            for block in response.content:
                if hasattr(block, 'text') and block.text.strip():
                    answer_text = block.text
                    break

        if answer_text:
            if strategy_name != "primary+context":
                logger.warning(
                    f"Succeeded with fallback strategy '{strategy_name}' "
                    f"after earlier refusal(s)."
                )
            break  # Success

        # Log the refusal and try next strategy
        logger.warning(
            f"[{strategy_name}] {model} refused "
            f"({len(chunks_to_use)} chunks). Trying next strategy."
        )

    t_llm = time.time()
    logger.info(
        f"Timing: RAG={t_rag - t_start:.2f}s, LLM={t_llm - t_rag:.2f}s, "
        f"total={t_llm - t_start:.2f}s"
    )

    # Final fallback if all strategies failed
    if answer_text is None:
        logger.error(
            f"All strategies failed for question: {question[:100]}"
        )
        answer_text = (
            "I was unable to generate an answer for this question after multiple attempts. "
            "Please try rephrasing your question, or try again later."
        )

    return {
        "answer": answer_text,
        "confidence": confidence_level,
        "sources": rag_result["citations"],
        "warnings": rag_result["warnings"],
        "rag_results": rag_result,
    }


# ===========================================================================
# Streaming Answer Generation (SSE)
# ===========================================================================

import json


def generate_answer_stream(question: str):
    """Generator that yields SSE events for streaming answer generation.

    Event types:
        status  — {"stage": "searching"} then {"stage": "generating", "confidence": ..., "sources": ...}
        chunk   — {"text": "..."} (individual Claude text tokens)
        complete — {"question_id": null} (signals stream end; caller sets question_id after DB save)
        error   — {"message": "..."} if something goes wrong

    Yields:
        str: Formatted SSE lines ("event: ...\ndata: ...\n\n")
    """
    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    # --- Phase 1: RAG retrieval ---
    yield _sse("status", {"stage": "searching"})

    t_start = time.time()
    try:
        rag_result = verified_query(question, top_k=12, use_reranker=True)
    except Exception as e:
        rag_result = {
            "query": question,
            "results": [],
            "confidence": {
                "level": "LOW",
                "top_score": 0.0,
                "num_results": 0,
                "num_high_confidence": 0,
                "num_sources": 0,
                "sources": [],
                "contradictions": [],
                "reasoning": f"RAG retrieval failed: {e}",
            },
            "citations": [],
            "warnings": [f"Knowledge base retrieval failed: {e}. Answer based on general knowledge only."],
            "gap_logged": False,
        }

    t_rag = time.time()

    confidence_level = rag_result["confidence"]["level"]
    confidence_reasoning = rag_result["confidence"]["reasoning"]
    sources = rag_result["citations"]
    warnings = rag_result["warnings"]

    # Build context chunks
    all_chunks = []
    for i, result in enumerate(rag_result["results"], 1):
        source = result.get("source", "unknown")
        score = result.get("rerank_score", 0.0)
        text = result.get("parent_text", "")
        all_chunks.append({
            "index": i,
            "source": source,
            "score": score,
            "text": text,
        })

    # When confidence is LOW, drop irrelevant chunks and tell Claude to
    # answer from its general domain knowledge instead.
    system_prompt = get_system_prompt()
    if confidence_level == "LOW":
        all_chunks = []
        system_prompt = get_system_prompt() + LOW_CONFIDENCE_ADDENDUM

    # --- Phase 2: Stream from Claude ---
    yield _sse("status", {
        "stage": "generating",
        "confidence": confidence_level,
        "sources": sources,
        "warnings": warnings,
    })

    # Build user message with context
    if all_chunks:
        context_parts = []
        for c in all_chunks:
            context_parts.append(
                f"--- Reference [{c['index']}]: {c['source']} "
                f"(relevance: {c['score']:.3f}) ---\n{c['text']}"
            )
        context_block = "\n\n".join(context_parts)

        # Deduplicated source summary for Claude's awareness
        from collections import Counter
        source_counts = Counter(c["source"] for c in all_chunks)
        source_lines = [
            f"  {i}. {src} — {cnt} chunk{'s' if cnt > 1 else ''}"
            for i, (src, cnt) in enumerate(source_counts.items(), 1)
        ]
        source_summary = "\n".join(source_lines)
    else:
        context_block = (
            "(No relevant documents found in the knowledge base. "
            "Answer using your expert knowledge and the reference "
            "data in your system instructions.)"
        )
        source_summary = "  (none)"

    user_message = f"""RETRIEVAL CONFIDENCE: {confidence_level}
{confidence_reasoning}

UNIQUE SOURCES RETRIEVED:
{source_summary}

RETRIEVED CONTEXT (internal engineering reference notes):
{context_block}

QUESTION:
{question}"""

    client = _get_client()
    full_answer = ""

    try:
        with client.messages.stream(
            model=STREAM_MODEL,
            max_tokens=4000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                full_answer += text
                yield _sse("chunk", {"text": text})
            final_msg = stream.get_final_message()
            log_llm_usage_sync(final_msg.usage, final_msg.model, "answering")
    except Exception as e:
        logger.error(f"[stream] Claude streaming error with {STREAM_MODEL}: {e}")
        # Fall back to non-streaming with fallback model
        try:
            response = client.messages.create(
                model=FALLBACK_MODEL,
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            log_llm_usage_sync(response.usage, response.model, "answering")
            if response.content:
                for block in response.content:
                    if hasattr(block, "text") and block.text.strip():
                        full_answer = block.text
                        yield _sse("chunk", {"text": full_answer})
                        break
        except Exception as e2:
            logger.error(f"[stream] Fallback also failed: {e2}")
            full_answer = (
                "I was unable to generate an answer for this question. "
                "Please try rephrasing your question, or try again later."
            )
            yield _sse("chunk", {"text": full_answer})

    t_llm = time.time()
    logger.info(
        f"[stream] Timing: RAG={t_rag - t_start:.2f}s, LLM={t_llm - t_rag:.2f}s, "
        f"total={t_llm - t_start:.2f}s"
    )

    # Final event with metadata (question_id set by caller after DB save)
    yield _sse("complete", {
        "answer": full_answer,
        "confidence": confidence_level,
        "sources": sources,
        "warnings": warnings,
    })
