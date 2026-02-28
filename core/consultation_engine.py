from __future__ import annotations
"""
Fluidoracle — Consultation Engine
===================================
Two-phase diagnostic consultation engine (vertical-agnostic):

Phase 1 (Gathering): Claude asks focused diagnostic questions to understand
the user's application. No RAG retrieval — pure domain knowledge from
the vertical's gathering prompt.

Phase 2 (Answering): Once Claude signals readiness, the backend constructs
a rich retrieval query from the full conversation, fires the hybrid retrieval
pipeline (scoped to the vertical's KB), and Claude delivers a grounded
recommendation with full citations.
"""

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

import anthropic
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CONSULT_MODEL = os.getenv("CONSULT_MODEL", "claude-sonnet-4-5-20250929")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "claude-sonnet-4-20250514")

print(f"[consultation_engine] Primary model: {CONSULT_MODEL}")
print(f"[consultation_engine] Fallback model: {FALLBACK_MODEL}")

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
# System Prompts
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# System Prompts — loaded from vertical config
# ---------------------------------------------------------------------------
# Legacy hardcoded prompts removed. Prompts are now loaded from:
#   platforms/<platform>/verticals/<vertical>/gathering_prompt.md
#   platforms/<platform>/verticals/<vertical>/answering_prompt.md
# The consultation engine receives these via VerticalConfig.

# Module-level defaults (set by init_vertical)
GATHERING_SYSTEM_PROMPT: str = ""
ANSWERING_SYSTEM_PROMPT_TEMPLATE: str = ""


def init_vertical(vertical_config) -> None:
    """Initialize module-level prompts from a vertical config."""
    global GATHERING_SYSTEM_PROMPT, ANSWERING_SYSTEM_PROMPT_TEMPLATE
    GATHERING_SYSTEM_PROMPT = vertical_config.gathering_prompt
    # The answering prompt is the vertical's full answering_prompt with
    # placeholders for {application_profile} and {rag_context}
    ANSWERING_SYSTEM_PROMPT_TEMPLATE = vertical_config.answering_prompt


def _get_answering_prompt(application_profile: str, rag_context: str) -> str:
    """Build the answering system prompt with RAG context injected."""
    base = ANSWERING_SYSTEM_PROMPT_TEMPLATE or ""
    return base + f"""

ADDITIONAL CONTEXT FOR THIS RESPONSE:

You are in the ANSWERING phase of a diagnostic consultation. The user has already provided detailed information about their application through a multi-turn conversation. The full conversation history is included below.

APPLICATION PROFILE:
{application_profile}

RETRIEVED TECHNICAL CONTEXT:
{rag_context}

YOUR TASK:
Based on the complete application profile gathered during the diagnostic phase AND the retrieved technical data, provide a comprehensive recommendation. Your recommendation MUST include:

1. RECOMMENDED SOLUTION — specific product(s) or approach with model numbers where available
2. WHY THIS SOLUTION — connect each element of the recommendation to specific application requirements gathered during diagnosis
3. KEY SPECIFICATIONS — with sources cited per existing citation discipline
4. TRADE-OFFS — what alternatives were considered and why this recommendation is preferred
5. CAVEATS — what assumptions you're making, what the user should verify, when they should consult a manufacturer directly
6. SYSTEM CONSIDERATIONS — if relevant for this domain

If the retrieved technical data doesn't contain specific product matches, say so explicitly and provide the best guidance you can from domain knowledge, clearly labeled per citation discipline.

For follow-up questions in this phase, maintain full context and refine or expand your recommendation based on new information."""



# Addendum appended ONLY for the initial recommendation (gathering→answering transition).
# Follow-up questions in the answering phase do NOT get this instruction.
INITIAL_RECOMMENDATION_FORMAT = """

RESPONSE FORMAT (CRITICAL — you MUST follow this exact structure):

Your response MUST be wrapped in exactly two XML sections. Do NOT include any text outside of these tags.

<chat_summary>
Write a concise, actionable recommendation in 300-400 words maximum. Include:

1. WHAT TO USE — specific product/approach with model name. Lead with this immediately in the first sentence.
2. WHY IT FITS — connect the recommendation to 2-3 of the user's most important requirements. Be specific but brief.
3. CRITICAL SUCCESS FACTORS — the 2-3 things that will make or break the installation. Format as a short numbered list.
4. EXPECTED RESULTS — one sentence on what similar installations have achieved, with source citation.

End with: "Expand the full technical report below for complete specifications, alternatives analysis, and system design guidance."

Style rules for the summary:
- No headers or section labels — write it as natural prose with one numbered list for the critical factors
- Get to the product recommendation in the first sentence
- Be specific (model numbers, pressures, temperatures) but don't exhaustively list every spec
- Cite sources inline but keep citations minimal — save detailed sourcing for the full report
</chat_summary>

<full_report>
Write a comprehensive technical report covering everything you would tell a client. This is the detailed reference document. Use clear section headers. Include:

## Recommended Solution
Full product specification with model numbers, materials, operating parameters. Cite all sources.

## Why This Solution
Detailed reasoning connecting every element of the recommendation to the application requirements gathered during consultation.

## Key Specifications
Complete technical specifications in a structured format. Flow rates, pressures, temperatures, materials, dimensions, connections, electrical requirements.

## Alternatives Considered
Each alternative with pros, cons, and verdict. Explain why it was rejected or ranked lower.

## System Considerations
Everything beyond the nozzle itself: pump requirements, filtration, piping, temperature control, mounting, instrumentation, compressed air, electrical, maintenance access.

## Caveats and Assumptions
What you're assuming about their application. What they need to verify before purchasing.

## Expected Performance
Quantified outcomes from similar installations with source citations.

## Next Steps
Specific procurement guidance: who to contact, what to request, what information to provide to the manufacturer.

Style rules for the full report:
- Use headers and structured formatting — this is a reference document
- Be thorough — include everything relevant
- Cite every claim using the existing citation discipline
- Include specific model numbers, part numbers, and ordering information where available
- This report may be printed, forwarded to colleagues, or attached to purchase requisitions
</full_report>"""


# Max gathering turns before we nudge Claude to wrap up
MAX_GATHERING_TURNS = 6

GATHERING_NUDGE = """

IMPORTANT: You have been gathering information for several turns now. You should either:
1. Signal readiness with the <consultation_signal> and provide your recommendation based on what you have, OR
2. Explicitly tell the user what ONE critical piece of information is still missing and why you need it before proceeding.

Do NOT ask more than one additional question. Wrap up the diagnostic phase."""


# ===========================================================================
# Signal Parsing
# ===========================================================================

def _parse_consultation_signal(text: str) -> dict | None:
    """Parse the <consultation_signal> XML from Claude's response.

    Returns dict with keys: ready, refined_query, application_domain, parameters
    or None if no valid signal found.
    """
    pattern = r"<consultation_signal>(.*?)</consultation_signal>"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None

    signal_xml = match.group(1)

    try:
        ready_match = re.search(r"<ready>(.*?)</ready>", signal_xml, re.DOTALL)
        query_match = re.search(r"<refined_query>(.*?)</refined_query>", signal_xml, re.DOTALL)
        domain_match = re.search(r"<application_domain>(.*?)</application_domain>", signal_xml, re.DOTALL)
        params_match = re.search(r"<parameters>(.*?)</parameters>", signal_xml, re.DOTALL)

        if not ready_match or ready_match.group(1).strip().lower() != "true":
            return None

        result = {
            "ready": True,
            "refined_query": query_match.group(1).strip() if query_match else "",
            "application_domain": domain_match.group(1).strip() if domain_match else "general",
            "parameters": {},
        }

        if params_match:
            try:
                result["parameters"] = json.loads(params_match.group(1).strip())
            except json.JSONDecodeError:
                logger.warning("Failed to parse parameters JSON in consultation signal")
                result["parameters"] = {"raw": params_match.group(1).strip()}

        return result

    except Exception as e:
        logger.error(f"Failed to parse consultation signal: {e}")
        return None


def _strip_consultation_signal(text: str) -> str:
    """Remove the <consultation_signal> block from the visible response.

    Also removes any orphaned signal XML fragments that may remain if
    the signal was truncated mid-stream (e.g., max_tokens cutoff).
    """
    # Remove complete signal blocks
    text = re.sub(
        r"\s*<consultation_signal>.*?</consultation_signal>\s*",
        "",
        text,
        flags=re.DOTALL,
    )

    # Remove any orphaned/truncated signal fragments
    _SIGNAL_FRAGMENTS = [
        r"</?consultation_signal[^>]*>?",
        r"</?ready[^>]*>?",
        r"</?refined_query[^>]*>?",
        r"</?application_domain[^>]*>?",
        r"</?parameters[^>]*>?",
    ]
    for frag in _SIGNAL_FRAGMENTS:
        text = re.sub(frag, "", text)

    # Also remove an unclosed <consultation_signal> block (truncated by max_tokens)
    text = re.sub(r"\s*<consultation_signal>.*", "", text, flags=re.DOTALL)

    return text.strip()


def _parse_recommendation_sections(text: str) -> tuple[str, str | None]:
    """Parse <chat_summary> and <full_report> from Claude's recommendation.

    Returns (summary_text, full_report_text).
    If tags are not found, returns (cleaned_text, None) as graceful fallback.
    """
    summary_match = re.search(
        r"<chat_summary>(.*?)</chat_summary>",
        text,
        re.DOTALL,
    )
    report_match = re.search(
        r"<full_report>(.*?)</full_report>",
        text,
        re.DOTALL,
    )

    if summary_match and report_match:
        return (
            summary_match.group(1).strip(),
            report_match.group(1).strip(),
        )

    # Graceful fallback: strip any partial/orphaned tags, return as summary-only
    cleaned = re.sub(r"</?(?:chat_summary|full_report)>", "", text).strip()
    return (cleaned, None)


# ===========================================================================
# Claude API call with fallback
# ===========================================================================

def _call_claude(system: str, messages: list[dict], max_tokens: int = 4000) -> tuple:
    """Call Claude API with automatic fallback on refusal.

    Returns (response_text, model_used).
    """
    client = _get_client()

    for model in [CONSULT_MODEL, FALLBACK_MODEL]:
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )

            logger.info(
                f"[consultation_engine] model={response.model} "
                f"stop_reason={response.stop_reason} "
                f"input_tokens={response.usage.input_tokens} "
                f"output_tokens={response.usage.output_tokens}"
            )
            log_llm_usage_sync(response.usage, response.model, "gathering")

            if response.stop_reason == "refusal" or not response.content:
                if model == FALLBACK_MODEL:
                    return ("Unable to generate a response. Please try rephrasing.", model)
                logger.warning(f"{model} refused. Retrying with {FALLBACK_MODEL}...")
                continue

            for block in response.content:
                if hasattr(block, "text"):
                    return (block.text, response.model)

            return ("The model returned a response but no text content.", response.model)

        except Exception as e:
            logger.error(f"[consultation_engine] API error with {model}: {e}")
            if model == FALLBACK_MODEL:
                return (f"An error occurred generating the response: {e}", model)
            continue

    return ("Unable to generate a response.", FALLBACK_MODEL)


def _call_claude_stream(system: str, messages: list[dict], max_tokens: int = 4000):
    """Stream Claude API response, yielding text deltas.

    Yields tuples of (event_type, data):
      ("text", delta_str)   — incremental text
      ("done", model_used)  — stream finished
      ("error", message)    — if an error occurs
    """
    client = _get_client()

    for model in [CONSULT_MODEL, FALLBACK_MODEL]:
        try:
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                full_text = ""
                for text in stream.text_stream:
                    full_text += text
                    yield ("text", text)

                # Get final message for logging
                response = stream.get_final_message()
                logger.info(
                    f"[consultation_engine] stream model={response.model} "
                    f"stop_reason={response.stop_reason} "
                    f"input_tokens={response.usage.input_tokens} "
                    f"output_tokens={response.usage.output_tokens}"
                )
                log_llm_usage_sync(response.usage, response.model, "gathering")

                if response.stop_reason == "refusal":
                    if model == FALLBACK_MODEL:
                        yield ("error", "Unable to generate a response. Please try rephrasing.")
                        return
                    logger.warning(f"{model} refused. Retrying with {FALLBACK_MODEL}...")
                    continue

                yield ("done", response.model)
                return

        except Exception as e:
            logger.error(f"[consultation_engine] stream API error with {model}: {e}")
            if model == FALLBACK_MODEL:
                yield ("error", f"An error occurred generating the response: {e}")
                return
            continue

    yield ("error", "Unable to generate a response.")


# ===========================================================================
# RAG Retrieval
# ===========================================================================

def _run_retrieval(query: str) -> dict:
    """Run the hybrid retrieval pipeline and return structured results."""
    try:
        rag_result = verified_query(
            query,
            top_k=12,
            use_reranker=True,
            semantic_weight=0.70,
            bm25_weight=0.30,
        )
    except Exception as e:
        logger.error(f"RAG retrieval failed: {e}")
        rag_result = {
            "query": query,
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
            "warnings": [f"Knowledge base retrieval failed: {e}."],
            "gap_logged": False,
        }
    return rag_result


def _build_rag_context(rag_result: dict) -> tuple[str, list[str]]:
    """Build context block and chunk ID list from RAG results.

    Returns (context_block_str, chunk_ids_list).
    """
    context_parts = []
    chunk_ids = []

    for i, result in enumerate(rag_result["results"], 1):
        source = result.get("source", "unknown")
        score = result.get("rerank_score", 0.0)
        text = result.get("parent_text", "")
        chunk_id = result.get("id", f"chunk_{i}")
        context_parts.append(
            f"--- Reference [{i}]: {source} (relevance: {score:.3f}) ---\n{text}"
        )
        chunk_ids.append(chunk_id)

    if context_parts:
        # Deduplicated source summary
        from collections import Counter
        source_counts = Counter(r.get("source", "unknown") for r in rag_result["results"])
        source_lines = [
            f"  {i}. {src} — {cnt} chunk{'s' if cnt > 1 else ''}"
            for i, (src, cnt) in enumerate(source_counts.items(), 1)
        ]
        source_summary = "\n".join(source_lines)

        context_block = f"""RETRIEVAL CONFIDENCE: {rag_result['confidence']['level']}
{rag_result['confidence']['reasoning']}

UNIQUE SOURCES RETRIEVED:
{source_summary}

RETRIEVED CONTEXT (internal engineering reference notes):
{chr(10).join(context_parts)}"""
    else:
        context_block = (
            "(No relevant documents found in the knowledge base. "
            "Answer using your expert knowledge and the reference "
            "data in your system instructions.)"
        )

    return context_block, chunk_ids


# ===========================================================================
# Main Consultation Response Generator
# ===========================================================================

def generate_consultation_response(
    session_id: str,
    user_message: str,
    phase: str,
    conversation_history: list[dict],
    gathered_parameters: dict | None = None,
    gathering_turn_count: int = 0,
    force_transition: bool = False,
) -> dict:
    """Generate a consultation response with phase-aware logic.

    Args:
        session_id: The consultation session ID
        user_message: The user's latest message
        phase: Current phase ('gathering' or 'answering')
        conversation_history: Prior messages [{"role": ..., "content": ...}, ...]
        gathered_parameters: Accumulated parameters from gathering phase
        gathering_turn_count: Number of user messages in gathering phase so far
        force_transition: If True, instruct Claude to transition immediately

    Returns:
        {
            "content": str,          # Visible response text (signal stripped)
            "phase": str,            # Phase after this turn
            "application_domain": str | None,
            "gathered_parameters": dict | None,
            "refined_query": str | None,
            "confidence": str | None,
            "sources": list[str],
            "rag_chunks_used": list[str] | None,
        }
    """
    if phase == "gathering":
        return _handle_gathering_phase(
            user_message=user_message,
            conversation_history=conversation_history,
            gathering_turn_count=gathering_turn_count,
            force_transition=force_transition,
        )
    else:
        # answering or complete phase — always do RAG
        return _handle_answering_phase(
            user_message=user_message,
            conversation_history=conversation_history,
            gathered_parameters=gathered_parameters,
        )


FORCE_TRANSITION_INSTRUCTION = """

CRITICAL OVERRIDE: The user has indicated they have no more information to provide. You MUST signal readiness immediately in this response. Do NOT ask any more questions. Summarize what you've learned, then include the <consultation_signal> with your best refined_query based on the information gathered so far. Even if you feel you're missing important details, proceed with what you have — the user cannot provide more."""


def _handle_gathering_phase(
    user_message: str,
    conversation_history: list[dict],
    gathering_turn_count: int,
    force_transition: bool = False,
) -> dict:
    """Handle a turn during the gathering phase."""

    # Build system prompt, potentially with nudge or force transition
    system = GATHERING_SYSTEM_PROMPT
    if force_transition:
        system += FORCE_TRANSITION_INSTRUCTION
    elif gathering_turn_count >= MAX_GATHERING_TURNS:
        system += GATHERING_NUDGE

    # Build messages array
    messages = []
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    # Call Claude (no RAG in gathering phase)
    response_text, model_used = _call_claude(system=system, messages=messages)
    logger.info(f"[gathering] Response from {model_used}")

    # Check for phase transition signal
    signal = _parse_consultation_signal(response_text)

    if signal:
        # Phase transition detected — strip signal and run Phase 2
        visible_response = _strip_consultation_signal(response_text)
        # Validate refined_query — fall back to conversation if empty
        retrieval_query = signal["refined_query"]
        if not retrieval_query or not retrieval_query.strip():
            logger.warning(
                "[gathering→answering] Empty refined_query from signal. "
                "Falling back to concatenated user messages for retrieval."
            )
            user_messages = [
                msg["content"] for msg in conversation_history
                if msg["role"] == "user"
            ]
            user_messages.append(user_message)
            retrieval_query = " ".join(user_messages)
            signal["refined_query"] = retrieval_query

        logger.info(
            f"[gathering→answering] Domain: {signal['application_domain']}, "
            f"Query length: {len(retrieval_query)}"
        )

        # Run RAG retrieval on the refined query
        rag_result = _run_retrieval(retrieval_query)
        rag_context, chunk_ids = _build_rag_context(rag_result)

        # Format the application profile from gathered parameters
        params = signal.get("parameters", {})
        if params:
            profile_lines = [f"  {k}: {v}" for k, v in params.items()]
            application_profile = "\n".join(profile_lines)
        else:
            application_profile = "(No structured parameters extracted)"

        # Build the answering system prompt with context filled in
        answering_prompt = _get_answering_prompt(
            application_profile=application_profile,
            rag_context=rag_context,
        )
        # Append the initial recommendation format instructions
        answering_prompt += "\n\n" + INITIAL_RECOMMENDATION_FORMAT

        # Build full conversation + user message for answering call
        answering_messages = []
        for msg in conversation_history:
            answering_messages.append({"role": msg["role"], "content": msg["content"]})
        answering_messages.append({"role": "user", "content": user_message})

        # Call Claude again with full context for the grounded recommendation
        answer_text, answer_model = _call_claude(
            system=answering_prompt,
            messages=answering_messages,
            max_tokens=8000,
        )
        logger.info(f"[answering] Recommendation from {answer_model}")

        # Strip any accidental signal from the answer
        answer_text = _strip_consultation_signal(answer_text)

        # Parse into summary + full report sections
        summary_text, full_report_text = _parse_recommendation_sections(answer_text)

        # Prepend transition summary to saved content
        saved_content = (visible_response + "\n\n" + summary_text) if visible_response.strip() else summary_text

        confidence = rag_result["confidence"]["level"]
        sources = rag_result["citations"]

        return {
            "content": saved_content,
            "full_report": full_report_text,
            "phase": "answering",
            "application_domain": signal["application_domain"],
            "gathered_parameters": signal["parameters"],
            "refined_query": signal["refined_query"],
            "confidence": confidence,
            "sources": sources,
            "rag_chunks_used": chunk_ids,
        }
    else:
        # No transition — still gathering
        return {
            "content": response_text,
            "phase": "gathering",
            "application_domain": None,
            "gathered_parameters": None,
            "refined_query": None,
            "confidence": None,
            "sources": [],
            "rag_chunks_used": None,
        }


def _handle_answering_phase(
    user_message: str,
    conversation_history: list[dict],
    gathered_parameters: dict | None = None,
) -> dict:
    """Handle a follow-up turn during the answering phase."""

    # Run RAG on the latest user message for follow-up context
    rag_result = _run_retrieval(user_message)
    rag_context, chunk_ids = _build_rag_context(rag_result)

    # Format application profile
    if gathered_parameters:
        profile_lines = [f"  {k}: {v}" for k, v in gathered_parameters.items()]
        application_profile = "\n".join(profile_lines)
    else:
        application_profile = "(See conversation history for application details)"

    answering_prompt = _get_answering_prompt(
        application_profile=application_profile,
        rag_context=rag_context,
    )

    # Build messages with full history
    messages = []
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    response_text, model_used = _call_claude(
        system=answering_prompt,
        messages=messages,
        max_tokens=6000,
    )
    logger.info(f"[answering follow-up] Response from {model_used}")

    # Strip any accidental signal
    response_text = _strip_consultation_signal(response_text)

    confidence = rag_result["confidence"]["level"]
    sources = rag_result["citations"]

    return {
        "content": response_text,
        "full_report": None,
        "phase": "answering",
        "application_domain": None,
        "gathered_parameters": None,
        "refined_query": None,
        "confidence": confidence,
        "sources": sources,
        "rag_chunks_used": chunk_ids,
    }


# ===========================================================================
# Streaming Variants
# ===========================================================================

def generate_consultation_response_stream(
    session_id: str,
    user_message: str,
    phase: str,
    conversation_history: list[dict],
    gathered_parameters: dict | None = None,
    gathering_turn_count: int = 0,
    force_transition: bool = False,
):
    """Streaming version of generate_consultation_response.

    Yields tuples of (event_type, data):
      ("status", str)           — status updates (e.g. "Searching knowledge base...")
      ("metadata", dict)        — phase/domain/params metadata (sent before text starts)
      ("text", str)             — incremental text deltas
      ("done", dict)            — final result dict (content, phase, rag_chunks_used, etc.)
      ("error", str)            — error message
    """
    if phase == "gathering":
        yield from _handle_gathering_phase_stream(
            user_message=user_message,
            conversation_history=conversation_history,
            gathering_turn_count=gathering_turn_count,
            force_transition=force_transition,
        )
    else:
        yield from _handle_answering_phase_stream(
            user_message=user_message,
            conversation_history=conversation_history,
            gathered_parameters=gathered_parameters,
        )


def _handle_gathering_phase_stream(
    user_message: str,
    conversation_history: list[dict],
    gathering_turn_count: int,
    force_transition: bool = False,
):
    """Streaming gathering phase. If no transition, stream the response.
    If transition detected, do RAG then stream the answering call.
    """
    system = GATHERING_SYSTEM_PROMPT
    if force_transition:
        system += FORCE_TRANSITION_INSTRUCTION
    elif gathering_turn_count >= MAX_GATHERING_TURNS:
        system += GATHERING_NUDGE

    messages = []
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    # First Claude call (gathering) — we need the full text to check for signal,
    # so we can't stream this one to the user. Use non-streaming call.
    response_text, model_used = _call_claude(system=system, messages=messages)
    logger.info(f"[gathering-stream] Response from {model_used}")

    signal = _parse_consultation_signal(response_text)

    if not signal:
        # No transition — just yield the gathering response as text
        visible_text = response_text
        yield ("metadata", {"phase": "gathering"})
        yield ("text", visible_text)
        yield ("done", {
            "content": visible_text,
            "phase": "gathering",
            "application_domain": None,
            "gathered_parameters": None,
            "refined_query": None,
            "confidence": None,
            "sources": [],
            "rag_chunks_used": None,
        })
        return

    # Phase transition detected — strip signal and do RAG + streaming answer
    visible_response = _strip_consultation_signal(response_text)
    retrieval_query = signal["refined_query"]
    if not retrieval_query or not retrieval_query.strip():
        logger.warning("[gathering→answering-stream] Empty refined_query. Falling back.")
        user_messages = [
            msg["content"] for msg in conversation_history if msg["role"] == "user"
        ]
        user_messages.append(user_message)
        retrieval_query = " ".join(user_messages)
        signal["refined_query"] = retrieval_query

    logger.info(f"[gathering→answering-stream] Domain: {signal['application_domain']}")

    # Send the gathering response text first (the transition summary)
    if visible_response.strip():
        yield ("text", visible_response + "\n\n")

    # Now do RAG retrieval
    yield ("status", "Searching knowledge base...")
    rag_result = _run_retrieval(retrieval_query)
    rag_context, chunk_ids = _build_rag_context(rag_result)

    # Build answering prompt
    params = signal.get("parameters", {})
    if params:
        profile_lines = [f"  {k}: {v}" for k, v in params.items()]
        application_profile = "\n".join(profile_lines)
    else:
        application_profile = "(No structured parameters extracted)"

    answering_prompt = _get_answering_prompt(
        application_profile=application_profile,
        rag_context=rag_context,
    )
    # Append the initial recommendation format instructions
    answering_prompt += "\n\n" + INITIAL_RECOMMENDATION_FORMAT

    answering_messages = []
    for msg in conversation_history:
        answering_messages.append({"role": msg["role"], "content": msg["content"]})
    answering_messages.append({"role": "user", "content": user_message})

    yield ("status", "Generating recommendation...")
    yield ("metadata", {
        "phase": "answering",
        "application_domain": signal["application_domain"],
        "gathered_parameters": signal["parameters"],
        "refined_query": signal["refined_query"],
    })

    # Section-aware streaming:
    # 1. Buffer tokens until </chat_summary> is found
    # 2. Emit summary content (tags stripped) as text chunks
    # 3. Emit ("section", "full_report") marker
    # 4. Stream full_report content live (stripping tags on the fly)
    # 5. Fallback: if 500+ chars without <chat_summary>, switch to passthrough
    streamed_text = ""
    buffer = ""
    section_mode = "buffering"  # buffering | summary_done | full_report | passthrough
    BUFFER_FALLBACK_LIMIT = 500

    for event_type, data in _call_claude_stream(
        system=answering_prompt,
        messages=answering_messages,
        max_tokens=8000,
    ):
        if event_type == "text":
            streamed_text += data

            if section_mode == "buffering":
                buffer += data
                # Check if we've found the end of chat_summary
                if "</chat_summary>" in buffer:
                    # Extract summary content, emit it
                    summary_match = re.search(
                        r"<chat_summary>(.*?)</chat_summary>", buffer, re.DOTALL
                    )
                    if summary_match:
                        summary_text = summary_match.group(1).strip()
                        yield ("text", summary_text)
                        # Check if full_report tag has started in the buffer
                        after_summary = buffer[buffer.index("</chat_summary>") + len("</chat_summary>"):]
                        if "<full_report>" in after_summary:
                            yield ("section", "full_report")
                            # Emit any content after <full_report> tag
                            report_start = after_summary.index("<full_report>") + len("<full_report>")
                            leftover = after_summary[report_start:]
                            if leftover.strip():
                                yield ("text", leftover)
                            section_mode = "full_report"
                        else:
                            # Reset buffer to just the part after </chat_summary>
                            buffer = after_summary
                            section_mode = "summary_done"
                    else:
                        # Malformed — fall back to passthrough
                        cleaned = re.sub(r"</?(?:chat_summary|full_report)>", "", buffer)
                        yield ("text", cleaned)
                        section_mode = "passthrough"
                elif len(buffer) > BUFFER_FALLBACK_LIMIT and "<chat_summary>" not in buffer:
                    # No XML tags — fallback to passthrough
                    yield ("text", buffer)
                    section_mode = "passthrough"

            elif section_mode == "summary_done":
                buffer += data  # Keep buffering until <full_report> tag
                if "<full_report>" in buffer:
                    yield ("section", "full_report")
                    report_start_idx = buffer.index("<full_report>") + len("<full_report>")
                    leftover = buffer[report_start_idx:]
                    if leftover.strip():
                        yield ("text", leftover)
                    section_mode = "full_report"
                    buffer = ""

            elif section_mode == "full_report":
                # Stream full_report content live, stripping closing tag if present
                chunk = data.replace("</full_report>", "")
                if chunk:
                    yield ("text", chunk)

            elif section_mode == "passthrough":
                # Fallback — stream everything as-is, stripping any XML tags
                chunk = re.sub(r"</?(?:chat_summary|full_report)>", "", data)
                if chunk:
                    yield ("text", chunk)

        elif event_type == "error":
            yield ("error", data)
            return

    # Parse the complete response for the final result
    answer_text = _strip_consultation_signal(streamed_text)
    summary_text, full_report_text = _parse_recommendation_sections(answer_text)

    confidence = rag_result["confidence"]["level"]
    sources = rag_result["citations"]

    # Prepend transition summary to the saved content (matches what was streamed)
    saved_content = (visible_response + "\n\n" + summary_text) if visible_response.strip() else summary_text

    yield ("done", {
        "content": saved_content,
        "full_report": full_report_text,
        "phase": "answering",
        "application_domain": signal["application_domain"],
        "gathered_parameters": signal["parameters"],
        "refined_query": signal["refined_query"],
        "confidence": confidence,
        "sources": sources,
        "rag_chunks_used": chunk_ids,
    })


def _handle_answering_phase_stream(
    user_message: str,
    conversation_history: list[dict],
    gathered_parameters: dict | None = None,
):
    """Stream a follow-up answer in the answering phase."""
    yield ("status", "Searching knowledge base...")
    rag_result = _run_retrieval(user_message)
    rag_context, chunk_ids = _build_rag_context(rag_result)

    if gathered_parameters:
        profile_lines = [f"  {k}: {v}" for k, v in gathered_parameters.items()]
        application_profile = "\n".join(profile_lines)
    else:
        application_profile = "(See conversation history for application details)"

    answering_prompt = _get_answering_prompt(
        application_profile=application_profile,
        rag_context=rag_context,
    )

    messages = []
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    yield ("status", "Generating recommendation...")
    yield ("metadata", {"phase": "answering"})

    streamed_text = ""
    for event_type, data in _call_claude_stream(
        system=answering_prompt,
        messages=messages,
        max_tokens=6000,
    ):
        if event_type == "text":
            streamed_text += data
            yield ("text", data)
        elif event_type == "error":
            yield ("error", data)
            return

    answer_text = _strip_consultation_signal(streamed_text)
    confidence = rag_result["confidence"]["level"]
    sources = rag_result["citations"]

    yield ("done", {
        "content": answer_text,
        "full_report": None,
        "phase": "answering",
        "application_domain": None,
        "gathered_parameters": None,
        "refined_query": None,
        "confidence": confidence,
        "sources": sources,
        "rag_chunks_used": chunk_ids,
    })


# ===========================================================================
# Session Title Generation (deterministic — no LLM call)
# ===========================================================================

def generate_session_title(first_message: str, vertical_display_name: str = "consultation") -> str:
    """Generate a short title from the first user message. No LLM call.

    Strategy: extract the first meaningful noun phrase (up to ~8 words) from
    the message. This captures the engineer's stated concern without burning
    an API call on what is essentially a text-truncation task.
    """
    # Strip markdown, URLs, excessive whitespace
    text = re.sub(r"https?://\S+", "", first_message)
    text = re.sub(r"[#*_`>]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return f"New {vertical_display_name.title()}"

    # Take the first sentence (or first 80 chars, whichever is shorter)
    first_sentence = re.split(r"[.!?\n]", text)[0].strip()
    if not first_sentence:
        first_sentence = text[:80]

    # Trim to ~8 words max
    words = first_sentence.split()
    if len(words) > 8:
        title = " ".join(words[:8]) + "…"
    else:
        title = " ".join(words)

    # Capitalize first letter, truncate to 60 chars
    title = title[0].upper() + title[1:] if title else f"New {vertical_display_name.title()}"
    if len(title) > 60:
        title = title[:57] + "..."

    return title
