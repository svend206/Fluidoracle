from __future__ import annotations
"""
Fluidoracle — Admin Routes
"""
import json
import logging
import os
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, StreamingResponse

import core.database as database
from core.models import KnowledgeUpdateRequest

ADMIN_KEY = os.getenv("ADMIN_KEY", "")

logger = logging.getLogger(__name__)

router = APIRouter()

# Routes: Admin (ADMIN_KEY-protected)
# ===========================================================================

def _verify_admin_key(x_admin_key: str | None):
    """Verify the admin key."""
    if not ADMIN_KEY:
        raise HTTPException(
            status_code=503,
            detail="Admin endpoints not configured. Set ADMIN_KEY in .env",
        )
    if not x_admin_key or x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key")


@router.delete("/api/admin/questions/{question_id}")
async def admin_delete_question(
    question_id: str,
    x_admin_key: str | None = Header(default=None),
):
    """Delete a question and all its associated votes and comments."""
    _verify_admin_key(x_admin_key)
    deleted = await database.delete_question(question_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"status": "deleted", "question_id": question_id}


@router.get("/api/admin/questions")
async def admin_list_questions(
    x_admin_key: str | None = Header(default=None),
):
    """List all questions with IDs (admin view for cleanup)."""
    _verify_admin_key(x_admin_key)
    questions = await database.get_questions(page=1, limit=100)
    return {
        "questions": [
            {
                "id": q["id"],
                "question": q["question"][:100],
                "confidence": q["confidence"],
                "answer_length": len(q["answer"]),
                "vote_up": q["vote_up"],
                "vote_down": q["vote_down"],
                "created_at": q["created_at"],
            }
            for q in questions
        ]
    }


@router.post("/api/admin/knowledge-updates")
async def admin_create_knowledge_update(
    req: KnowledgeUpdateRequest,
    x_admin_key: str | None = Header(default=None),
):
    """Record a knowledge base update and optionally notify matching subscribers."""
    _verify_admin_key(x_admin_key)

    update = await database.create_knowledge_update(
        title=req.title,
        description=req.description,
        domains=req.domains,
        topics=req.topics,
    )

    # Find matching users via consultation_sessions.user_id
    matched = await database.get_matching_subscribers_for_update(
        domains=req.domains,
    )

    # Send notifications
    from core.email_utils import send_knowledge_update_notification, is_email_configured

    notified = 0
    if is_email_configured() and matched:
        for sub in matched:
            sent = send_knowledge_update_notification(
                email=sub["email"],
                update_title=req.title,
                update_description=req.description,
                session_title=sub.get("session_title", "Your consultation"),
                unsubscribe_token=sub.get("unsubscribe_token", ""),
            )
            if sent:
                notified += 1

    return {
        "update": update,
        "subscribers_matched": len(matched),
        "notifications_sent": notified,
    }


@router.get("/api/admin/demand-signals")
async def admin_demand_signals(
    x_admin_key: str | None = Header(default=None),
    limit: int = 50,
):
    """View off-vertical demand signals — what engineers are asking for
    that the current vertical doesn't cover."""
    _verify_admin_key(x_admin_key)

    import aiosqlite
    db_path = database._get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT source_vertical, detected_target_vertical,
                      query_text, timestamp, session_id
               FROM off_vertical_demand
               ORDER BY timestamp DESC
               LIMIT ?""",
            (limit,),
        )

    async with aiosqlite.connect(db_path) as db:
        summary_rows = await db.execute_fetchall(
            """SELECT source_vertical, detected_target_vertical, COUNT(*) as count
               FROM off_vertical_demand
               GROUP BY source_vertical, detected_target_vertical
               ORDER BY count DESC""",
        )

    return {
        "total": len(rows),
        "summary": [{"from": r[0], "to": r[1], "count": r[2]} for r in summary_rows],
        "signals": [
            {
                "source_vertical": r["source_vertical"],
                "target_vertical": r["detected_target_vertical"],
                "query": r["query_text"],
                "timestamp": r["timestamp"],
                "session_id": r["session_id"],
            }
            for r in rows
        ],
    }


@router.get("/api/admin/llm-costs")
async def admin_llm_costs(
    x_admin_key: str | None = Header(default=None),
    days: int = 30,
):
    """View LLM usage costs, grouped by vertical and phase."""
    _verify_admin_key(x_admin_key)

    import aiosqlite
    db_path = database._get_db_path()
    async with aiosqlite.connect(db_path) as db:
        rows = await db.execute_fetchall(
            """SELECT vertical_id, phase, model,
                      COUNT(*) as calls,
                      SUM(input_tokens) as total_input,
                      SUM(output_tokens) as total_output,
                      SUM(estimated_cost_usd) as total_cost
               FROM llm_usage
               WHERE timestamp > datetime('now', ?)
               GROUP BY vertical_id, phase, model
               ORDER BY total_cost DESC""",
            (f"-{days} days",),
        )
        totals = await db.execute_fetchall(
            """SELECT COUNT(*), SUM(input_tokens), SUM(output_tokens),
                      SUM(estimated_cost_usd)
               FROM llm_usage
               WHERE timestamp > datetime('now', ?)""",
            (f"-{days} days",),
        )

    total = totals[0] if totals else (0, 0, 0, 0)
    return {
        "period_days": days,
        "totals": {
            "calls": total[0],
            "input_tokens": total[1],
            "output_tokens": total[2],
            "estimated_cost_usd": round(total[3] or 0, 4),
        },
        "breakdown": [
            {
                "vertical": r[0], "phase": r[1], "model": r[2],
                "calls": r[3], "input_tokens": r[4], "output_tokens": r[5],
                "estimated_cost_usd": round(r[6] or 0, 4),
            }
            for r in rows
        ],
    }
