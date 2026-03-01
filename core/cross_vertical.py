"""
Fluidoracle — Cross-Vertical Intelligence
==========================================
Embedding-based off-vertical query detection. Runs alongside every
consultation message at near-zero cost (one embedding call per message,
which we're already making for retrieval).

See docs/compute-strategy.md § "Off-vertical query detection".
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module state (populated by init_cross_vertical)
# ---------------------------------------------------------------------------

_vertical_embeddings: dict[str, np.ndarray] = {}  # vertical_id → embedding vector
_vertical_descriptions: dict[str, str] = {}       # vertical_id → description text
_current_vertical_id: str = ""
_current_platform_id: str = ""
_db_path: str = ""
_initialized: bool = False


def init_cross_vertical(
    platform_id: str,
    verticals: dict,  # {vertical_id: VerticalConfig}
    db_path: str,
) -> None:
    """Initialize cross-vertical detection. Call once at startup.

    Embeds all vertical descriptions for later cosine similarity scoring.
    Only useful when 2+ verticals exist.
    """
    global _vertical_embeddings, _vertical_descriptions
    global _current_platform_id, _db_path, _initialized

    _current_platform_id = platform_id
    _db_path = db_path

    if len(verticals) < 2:
        logger.info("[cross-vertical] Single vertical — detection disabled.")
        _initialized = False
        return

    # Embed vertical descriptions
    try:
        from core.retrieval.hybrid_search import _get_openai
        from core.retrieval.config import EMBEDDING_MODEL

        descriptions = {}
        for vid, vc in verticals.items():
            # Use description + example questions for richer embedding
            text = vc.description
            if vc.example_questions:
                text += "\n" + "\n".join(vc.example_questions[:3])
            descriptions[vid] = text

        texts = list(descriptions.values())
        vids = list(descriptions.keys())

        response = _get_openai().embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )

        for i, vid in enumerate(vids):
            _vertical_embeddings[vid] = np.array(response.data[i].embedding)
            _vertical_descriptions[vid] = descriptions[vid]

        _initialized = True
        logger.info(
            f"[cross-vertical] Initialized with {len(vids)} verticals: {vids}"
        )

    except Exception as e:
        logger.warning(f"[cross-vertical] Init failed: {e} — detection disabled.")
        _initialized = False


def check_off_vertical(
    message_text: str,
    current_vertical_id: str,
    session_id: str | None = None,
) -> Optional[dict]:
    """Check if a user message is off-vertical.

    Returns a dict with detection info if off-vertical demand is detected,
    or None if the message is on-topic.

    Cost: one embedding API call (same model used for retrieval).
    """
    if not _initialized or len(_vertical_embeddings) < 2:
        return None

    if current_vertical_id not in _vertical_embeddings:
        return None

    try:
        from core.retrieval.hybrid_search import _get_openai
        from core.retrieval.config import EMBEDDING_MODEL

        # Embed the user message
        response = _get_openai().embeddings.create(
            model=EMBEDDING_MODEL,
            input=[message_text],
        )
        msg_embedding = np.array(response.data[0].embedding)

        # Cosine similarity against all verticals
        scores = {}
        for vid, v_emb in _vertical_embeddings.items():
            scores[vid] = float(_cosine_similarity(msg_embedding, v_emb))

        current_score = scores.get(current_vertical_id, 0)
        best_other_vid = max(
            (vid for vid in scores if vid != current_vertical_id),
            key=lambda v: scores[v],
        )
        best_other_score = scores[best_other_vid]

        # Detection threshold: other vertical scores higher AND the gap is meaningful
        THRESHOLD_GAP = 0.03  # other must beat current by at least this much
        THRESHOLD_MIN = 0.30  # other must score at least this high

        if best_other_score > current_score + THRESHOLD_GAP and best_other_score >= THRESHOLD_MIN:
            result = {
                "detected": True,
                "current_vertical": current_vertical_id,
                "current_score": round(current_score, 4),
                "target_vertical": best_other_vid,
                "target_score": round(best_other_score, 4),
                "all_scores": {v: round(s, 4) for v, s in scores.items()},
            }

            # Log to database
            _log_demand(
                session_id=session_id,
                source_vertical=current_vertical_id,
                detected_target=best_other_vid,
                query_text=message_text[:500],
            )

            logger.info(
                f"[cross-vertical] Off-vertical detected: "
                f"{current_vertical_id} ({current_score:.3f}) → "
                f"{best_other_vid} ({best_other_score:.3f})"
            )
            return result

        return None

    except Exception as e:
        logger.warning(f"[cross-vertical] Check failed: {e}")
        return None


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return dot / norm


def _log_demand(
    session_id: str | None,
    source_vertical: str,
    detected_target: str,
    query_text: str,
) -> None:
    """Log off-vertical demand to the database (sync, non-blocking)."""
    if not _db_path:
        return
    try:
        conn = sqlite3.connect(_db_path)
        conn.execute(
            """INSERT INTO off_vertical_demand
               (session_id, source_vertical, source_platform,
                detected_target_vertical, query_text)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, source_vertical, _current_platform_id,
             detected_target, query_text),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[cross-vertical] Failed to log demand: {e}")
