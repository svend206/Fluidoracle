from __future__ import annotations
"""
Fluidoracle — Authentication Routes
"""
import json
import logging
import os
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, StreamingResponse

import core.database as database
import secrets
from datetime import datetime, timedelta, timezone

from core.models import AuthSendCodeRequest, AuthVerifyCodeRequest, ClaimSessionsRequest

async def get_current_user(authorization):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "")
    return await database.get_user_by_token(token)

logger = logging.getLogger(__name__)

router = APIRouter()

# Routes: Passwordless Authentication
# ===========================================================================

@router.post("/api/auth/send-code")
async def auth_send_code(req: AuthSendCodeRequest, request: Request):
    """Send a 6-digit verification code to the user's email."""
    import random
    from datetime import datetime as _dt, timedelta, timezone as _tz

    email = req.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="Invalid email address")

    # Rate limiting: max 3 codes per email per hour
    one_hour_ago = (_dt.now(_tz.utc) - timedelta(hours=1)).isoformat()
    recent_count = await database.count_recent_auth_codes(email, one_hour_ago)
    if recent_count >= 3:
        raise HTTPException(status_code=429, detail="Too many codes requested. Try again later.")

    # Create or get user
    unsubscribe_token = str(uuid.uuid4())
    user = await database.get_or_create_user(email, unsubscribe_token)

    # Generate 6-digit code
    code = f"{random.randint(0, 999999):06d}"
    expires_at = (_dt.now(_tz.utc) + timedelta(minutes=10)).isoformat()

    await database.create_auth_code(email, code, expires_at)

    # Send via email
    from core.email_utils import send_auth_code, is_email_configured

    if is_email_configured():
        sent = send_auth_code(email, code)
        if not sent:
            logger.warning(f"[auth] Failed to send code to {email}")
    else:
        logger.info(f"[auth] SMTP not configured — code for {email}: {code}")

    return {"success": True, "message": "Code sent to your email"}


@router.post("/api/auth/verify-code")
async def auth_verify_code(req: AuthVerifyCodeRequest):
    """Verify a 6-digit code and return a session token."""
    from datetime import datetime as _dt, timedelta, timezone as _tz

    email = req.email.strip().lower()
    code = req.code.strip()

    valid = await database.verify_auth_code(email, code)
    if not valid:
        return {"success": False, "message": "Invalid or expired code"}

    # Look up the user
    user = await database.get_user_by_email(email)
    if user is None:
        raise HTTPException(status_code=500, detail="User record not found after verification")

    # Create session token (90 days)
    expires_at = (_dt.now(_tz.utc) + timedelta(days=90)).isoformat()
    token = await database.create_auth_session(user["id"], expires_at)

    return {
        "success": True,
        "token": token,
        "user_id": user["id"],
        "email": user["email"],
    }


@router.post("/api/auth/logout")
async def auth_logout(authorization: str | None = Header(default=None)):
    """Invalidate the current session token."""
    if not authorization:
        return {"success": True}
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    await database.delete_auth_session(token)
    return {"success": True}


@router.get("/api/auth/me")
async def auth_me(authorization: str | None = Header(default=None)):
    """Get the current authenticated user, or 401."""
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "user_id": user["id"],
        "email": user["email"],
        "topic_subscription": user["topic_subscription"],
        "feature_updates": user["feature_updates"],
    }


@router.post("/api/auth/claim-sessions")
async def auth_claim_sessions(
    req: ClaimSessionsRequest,
    authorization: str | None = Header(default=None),
):
    """Claim anonymous consultation sessions for the authenticated user."""
    user = await get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    claimed = await database.claim_sessions(user["id"], req.session_ids)
    return {"claimed": claimed}


@router.get("/api/consult/unsubscribe/{unsubscribe_token}")
async def unsubscribe_user(unsubscribe_token: str):
    """One-click unsubscribe from all FilterOracle emails."""
    result = await database.unsubscribe_user(unsubscribe_token)

    if result is None:
        return HTMLResponse(
            content="""
            <html><body style="font-family: sans-serif; max-width: 500px; margin: 60px auto; text-align: center;">
                <h2 style="color: #dc2626;">Unsubscribe Failed</h2>
                <p style="color: #555;">This unsubscribe link is invalid.</p>
            </body></html>
            """,
            status_code=400,
        )

    return HTMLResponse(
        content=f"""
        <html><body style="font-family: sans-serif; max-width: 500px; margin: 60px auto; text-align: center;">
            <h2 style="color: #1e3a5f;">Unsubscribed</h2>
            <p style="color: #555;">
                <strong>{result['email']}</strong> has been unsubscribed from FilterOracle emails.
                You can re-enable notifications in your account settings anytime.
            </p>
        </body></html>
        """,
        status_code=200,
    )


# ===========================================================================
