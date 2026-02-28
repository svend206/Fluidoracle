from __future__ import annotations
"""
Fluidoracle — Invention Routes
"""
import json
import logging
import os
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, StreamingResponse

import core.database as database
from core.models import InventAuthRequest, InventSessionRequest, InventMessageRequest

INVENT_PASSPHRASE = os.getenv("INVENT_PASSPHRASE", "")

logger = logging.getLogger(__name__)

router = APIRouter()

# Routes: Invention Sessions (private, passphrase-protected)
# ===========================================================================

def _verify_invent_token(x_invent_token: str | None):
    """Verify the invention session passphrase."""
    if not INVENT_PASSPHRASE:
        raise HTTPException(
            status_code=503,
            detail="Invention sessions not configured. Set INVENT_PASSPHRASE in .env",
        )
    if not x_invent_token or x_invent_token != INVENT_PASSPHRASE:
        raise HTTPException(status_code=401, detail="Invalid passphrase")


@router.post("/api/invent/auth")
async def invent_auth(req: InventAuthRequest):
    """Validate the invention session passphrase."""
    if not INVENT_PASSPHRASE:
        raise HTTPException(
            status_code=503,
            detail="Invention sessions not configured. Set INVENT_PASSPHRASE in .env",
        )
    if req.passphrase != INVENT_PASSPHRASE:
        raise HTTPException(status_code=401, detail="Invalid passphrase")
    return {"status": "ok"}


@router.get("/api/invent/sessions")
async def list_invent_sessions(x_invent_token: str | None = Header(default=None)):
    """List all invention sessions."""
    _verify_invent_token(x_invent_token)
    sessions = await database.get_invention_sessions()
    return {"sessions": sessions}


@router.post("/api/invent/sessions")
async def create_invent_session(
    req: InventSessionRequest,
    x_invent_token: str | None = Header(default=None),
):
    """Create a new invention session."""
    _verify_invent_token(x_invent_token)
    session = await database.create_invention_session(title=req.title)
    return session


@router.get("/api/invent/sessions/{session_id}")
async def get_invent_session(
    session_id: str,
    x_invent_token: str | None = Header(default=None),
):
    """Get an invention session with all messages."""
    _verify_invent_token(x_invent_token)
    session = await database.get_invention_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/api/invent/sessions/{session_id}")
async def delete_invent_session(
    session_id: str,
    x_invent_token: str | None = Header(default=None),
):
    """Delete an invention session and all its messages."""
    _verify_invent_token(x_invent_token)
    deleted = await database.delete_invention_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


@router.post("/api/invent/sessions/{session_id}/messages")
async def send_invent_message(
    session_id: str,
    req: InventMessageRequest,
    x_invent_token: str | None = Header(default=None),
):
    """Send a message in an invention session and get an AI response."""
    _verify_invent_token(x_invent_token)

    # Verify session exists
    session = await database.get_invention_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_content = strip_html(req.content.strip())

    # Save the user message
    user_msg = await database.add_invention_message(
        session_id=session_id,
        role="user",
        content=user_content,
    )

    # Build conversation history from existing messages
    conversation_history = [
        {"role": m["role"], "content": m["content"]}
        for m in session["messages"]
    ]

    # Generate AI response
    from core.invention_engine import generate_invention_response, generate_session_title

    try:
        result = generate_invention_response(
            user_message=user_content,
            conversation_history=conversation_history,
        )
    except Exception as e:
        logger.error(f"Invention response failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Response generation failed: {e}")

    # Save the assistant message
    assistant_msg = await database.add_invention_message(
        session_id=session_id,
        role="assistant",
        content=result["content"],
        sources=result["sources"],
        confidence=result["confidence"],
    )

    # Auto-title on first message pair
    if len(session["messages"]) == 0:
        try:
            title = generate_session_title(user_content)
            await database.update_invention_session_title(session_id, title)
        except Exception:
            pass  # Non-critical, keep default title

    return {
        "user_message": user_msg,
        "assistant_message": assistant_msg,
    }


# ===========================================================================
