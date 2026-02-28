from __future__ import annotations
"""
Hydraulic Filter Platform — Training Data Logger (Programmatic Wrapper)
====================================================================
Wraps the existing training_logger's file paths to log platform
interactions as training data — without using the interactive CLI.

Training data is written to the same JSONL files the existing pipeline
uses (08-training-data/), so exports and stats still work.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add knowledge base to path for config import
_KB_DIR = Path(__file__).parent.parent / "ai" / "02-knowledge-base"
if str(_KB_DIR) not in sys.path:
    sys.path.insert(0, str(_KB_DIR))

from core.retrieval.config import TRAINING_DATA_DIR  # noqa: E402

# Paths (same as training_logger.py uses)
QA_LOG = TRAINING_DATA_DIR / "qa_pairs.jsonl"
CORRECTIONS_LOG = TRAINING_DATA_DIR / "corrections.jsonl"


def log_answered_question(
    question: str,
    answer: str,
    confidence: str,
    sources: list[str],
    question_id: str = "",
) -> bool:
    """Log a Q&A pair from the platform as training data.

    Returns True on success, False on error (never raises).
    """
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "qa_pair",
            "question": question,
            "answer": answer,
            "confidence": confidence,
            "sources": sources,
            "quality_reviewed": False,
            "origin": "platform",
            "question_id": question_id,
        }

        QA_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(QA_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return True
    except Exception:
        return False


def log_user_correction(
    question: str,
    original_answer: str,
    correction_text: str,
    question_id: str = "",
) -> bool:
    """Log a user-submitted correction as training data.

    These are the most valuable training examples.
    Returns True on success, False on error (never raises).
    """
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "correction",
            "question": question,
            "wrong_answer": original_answer,
            "correct_answer": correction_text,
            "explanation": "",
            "source": "platform_user",
            "question_id": question_id,
        }

        CORRECTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CORRECTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return True
    except Exception:
        return False


def log_upvoted_question(
    question: str,
    answer: str,
    confidence: str,
    sources: list[str],
    upvote_count: int,
    question_id: str = "",
) -> bool:
    """Log a heavily-upvoted Q&A as a high-quality training example.

    Called when a question crosses the upvote threshold (3+).
    Returns True on success, False on error (never raises).
    """
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "qa_pair",
            "question": question,
            "answer": answer,
            "confidence": confidence,
            "sources": sources,
            "quality_reviewed": True,
            "origin": "platform_upvoted",
            "upvote_count": upvote_count,
            "question_id": question_id,
        }

        QA_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(QA_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return True
    except Exception:
        return False


def log_downvoted_question(
    question: str,
    answer: str,
    confidence: str,
    sources: list[str],
    downvote_count: int,
    question_id: str = "",
) -> bool:
    """Log a downvoted Q&A as a low-quality training signal.

    Downvoted answers are valuable negative examples — they tell us
    what the model got wrong so we can correct it during fine-tuning.
    Returns True on success, False on error (never raises).
    """
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "qa_pair",
            "question": question,
            "answer": answer,
            "confidence": confidence,
            "sources": sources,
            "quality_reviewed": True,
            "origin": "platform_downvoted",
            "downvote_count": downvote_count,
            "question_id": question_id,
        }

        CORRECTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CORRECTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return True
    except Exception:
        return False


CONSULTATIONS_LOG = TRAINING_DATA_DIR / "consultations.jsonl"


def log_consultation(
    session_id: str,
    application_domain: str,
    gathered_parameters: dict,
    refined_query: str,
    messages: list[dict],
    rag_chunks_used: list[str],
    confidence: str,
    num_gathering_turns: int,
    recommendation_summary: str | None = None,
    recommendation_full_report: str | None = None,
) -> bool:
    """Log a completed consultation as training data.

    Each consultation is a full case study: multi-turn diagnostic → grounded recommendation.
    Returns True on success, False on error (never raises).
    """
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "consultation",
            "session_id": session_id,
            "application_domain": application_domain,
            "gathered_parameters": gathered_parameters,
            "refined_query": refined_query,
            "num_gathering_turns": num_gathering_turns,
            "messages": messages,
            "rag_chunks_used": rag_chunks_used,
            "confidence": confidence,
            "feedback": None,
            "recommendation_summary": recommendation_summary,
            "recommendation_full_report": recommendation_full_report,
        }

        CONSULTATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CONSULTATIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return True
    except Exception:
        return False


def log_consultation_feedback(
    session_id: str,
    rating: str,
    comment: str = "",
) -> bool:
    """Log user feedback for a consultation session.

    Returns True on success, False on error (never raises).
    """
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "consultation_feedback",
            "session_id": session_id,
            "feedback": {
                "rating": rating,
                "comment": comment,
            },
        }

        CONSULTATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CONSULTATIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return True
    except Exception:
        return False


OUTCOMES_LOG = TRAINING_DATA_DIR / "outcomes.jsonl"


def log_consultation_outcome(
    session_id: str,
    outcome_id: str,
    application_domain: str,
    gathered_parameters: dict,
    recommendation_summary: str,
    followup_stage: str,
    implementation_status: str | None,
    performance_rating: int | None,
    performance_notes: str | None,
    failure_occurred: bool,
    failure_mode: str | None,
    operating_conditions_matched: bool | None,
    would_recommend_same: bool | None,
) -> bool:
    """Log a consultation outcome as training data.

    Each outcome record is self-contained with enough context from the
    original consultation to be useful for analysis without joining.
    Returns True on success, False on error (never raises).
    """
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "outcome",
            "session_id": session_id,
            "outcome_id": outcome_id,
            "application_domain": application_domain,
            "gathered_parameters": gathered_parameters,
            "recommendation_summary": recommendation_summary,
            "followup_stage": followup_stage,
            "implementation_status": implementation_status,
            "performance_rating": performance_rating,
            "performance_notes": performance_notes,
            "failure_occurred": failure_occurred,
            "failure_mode": failure_mode,
            "operating_conditions_matched": operating_conditions_matched,
            "would_recommend_same": would_recommend_same,
        }

        OUTCOMES_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTCOMES_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return True
    except Exception:
        return False


def get_training_stats() -> dict:
    """Get training data accumulation stats."""
    qa_count = _count_lines(QA_LOG)
    correction_count = _count_lines(CORRECTIONS_LOG)
    consultation_count = _count_lines(CONSULTATIONS_LOG)
    outcome_count = _count_lines(OUTCOMES_LOG)

    return {
        "qa_pairs": qa_count,
        "corrections": correction_count,
        "consultations": consultation_count,
        "outcomes": outcome_count,
        "total": qa_count + correction_count + consultation_count + outcome_count,
    }


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())
