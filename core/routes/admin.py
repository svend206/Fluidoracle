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


# ===========================================================================
