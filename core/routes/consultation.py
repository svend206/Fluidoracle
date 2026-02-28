from __future__ import annotations
"""
Fluidoracle — Consultation Routes
"""
import json
import logging
import os
import re
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, StreamingResponse

import core.database as database


def strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text)
from core.models import (
    ConsultSessionRequest, ConsultMessageRequest,
    ConsultFeedbackRequest, ConsultOutcomeRequest, ConsultOutcomeUpdateRequest,
)
from core.vertical_loader import load_platform

PLATFORM_ID = os.getenv("PLATFORM_ID", "fps")

logger = logging.getLogger(__name__)


def _resolve_vertical_config(session: dict):
    """Look up the VerticalConfig for a session's vertical_id.
    Returns None if the vertical can't be resolved (falls back to module defaults).
    """
    vid = session.get("vertical_id")
    pid = session.get("platform_id") or PLATFORM_ID
    if not vid:
        return None
    try:
        platform = load_platform(pid)
        return platform.verticals.get(vid)
    except Exception:
        return None


async def get_current_user(authorization):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "")
    return await database.get_user_by_token(token)


router = APIRouter()

# Routes: Consultation Sessions (public, no auth required)
# ===========================================================================

@router.post("/api/consult/sessions")
async def create_consult_session(
    req: ConsultSessionRequest,
    authorization: str | None = Header(default=None),
):
    """Create a new consultation session, linked to user if authenticated."""
    session = await database.create_consultation_session(
        title=req.title,
        vertical_id=getattr(req, "vertical_id", None) or list(load_platform(PLATFORM_ID).verticals.keys())[0],
        platform_id=PLATFORM_ID,
    )
    # If authenticated, link session to user
    user = await get_current_user(authorization)
    if user:
        await database.update_consultation_session(session["id"], user_id=user["id"])
    return session


@router.get("/api/consult/sessions")
async def list_consult_sessions(authorization: str | None = Header(default=None)):
    """List consultation sessions. Authenticated: user's sessions. Anonymous: empty list."""
    user = await get_current_user(authorization)
    if user:
        sessions = await database.get_user_consultation_sessions(user["id"])
    else:
        sessions = []
    return {"sessions": sessions}


@router.get("/api/consult/sessions/{session_id}")
async def get_consult_session(session_id: str):
    """Get a consultation session with all messages."""
    session = await database.get_consultation_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/api/consult/sessions/{session_id}")
async def delete_consult_session(session_id: str):
    """Delete a consultation session and all its messages."""
    deleted = await database.delete_consultation_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}


@router.post("/api/consult/sessions/{session_id}/messages")
async def send_consult_message(session_id: str, req: ConsultMessageRequest):
    """Send a message in a consultation session and get an AI response."""
    session = await database.get_consultation_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Handle force_transition: use canned message and flag
    is_force_transition = req.force_transition and session["phase"] == "gathering"
    if is_force_transition:
        user_content = (
            "That's all the information I have available. "
            "Please go ahead with your recommendation based on what we've discussed."
        )
    else:
        user_content = strip_html(req.content.strip())
        if not user_content:
            raise HTTPException(status_code=422, detail="Message content is required")

    # Save the user message
    user_msg = await database.add_consultation_message(
        session_id=session_id,
        role="user",
        content=user_content,
        phase_at_time=session["phase"],
    )

    # Build conversation history from existing messages
    conversation_history = [
        {"role": m["role"], "content": m["content"]}
        for m in session["messages"]
    ]

    # Count gathering-phase user turns
    gathering_turn_count = sum(
        1 for m in session["messages"]
        if m["role"] == "user" and m["phase_at_time"] == "gathering"
    )
    if session["phase"] == "gathering":
        gathering_turn_count += 1  # Include current message

    # Resolve vertical config for this session
    _vc = _resolve_vertical_config(session)

    # Generate AI response
    from core.consultation_engine import generate_consultation_response, generate_session_title

    try:
        result = generate_consultation_response(
            session_id=session_id,
            user_message=user_content,
            phase=session["phase"],
            conversation_history=conversation_history,
            gathered_parameters=session.get("gathered_parameters"),
            gathering_turn_count=gathering_turn_count,
            force_transition=is_force_transition,
            vertical_config=_vc,
        )
    except Exception as e:
        logger.error(f"Consultation response failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Response generation failed: {e}")

    # If phase transitioned, update session metadata
    new_phase = result.get("phase", session["phase"])
    update_kwargs = {}

    if new_phase != session["phase"]:
        update_kwargs["phase"] = new_phase

    if result.get("application_domain"):
        update_kwargs["application_domain"] = result["application_domain"]

    if result.get("gathered_parameters"):
        update_kwargs["gathered_parameters"] = result["gathered_parameters"]

    if update_kwargs:
        await database.update_consultation_session(session_id, **update_kwargs)

    # Save the assistant message
    assistant_msg = await database.add_consultation_message(
        session_id=session_id,
        role="assistant",
        content=result["content"],
        phase_at_time=new_phase,
        rag_chunks_used=result.get("rag_chunks_used"),
        full_report=result.get("full_report"),
    )

    # Auto-title on first message pair
    if len(session["messages"]) == 0:
        try:
            title = generate_session_title(user_content)
            await database.update_consultation_session(session_id, title=title)
        except Exception:
            pass  # Non-critical

    # Log consultation training data and schedule follow-ups when we transition to answering
    if new_phase == "answering" and session["phase"] == "gathering":
        # Build phase-annotated message history for training data.
        # session["messages"] has phase_at_time from the DB; use it directly.
        annotated_messages = [
            {
                "role": m["role"],
                "content": m["content"],
                "phase": m.get("phase_at_time") or "gathering",
            }
            for m in session["messages"]
        ]
        # Add the current turn's messages (user = gathering, assistant = answering)
        annotated_messages.append(
            {"role": "user", "content": user_content, "phase": "gathering"}
        )
        annotated_messages.append(
            {"role": "assistant", "content": result["content"], "phase": "answering"}
        )

        training.log_consultation(
            session_id=session_id,
            application_domain=result.get("application_domain", "general"),
            gathered_parameters=result.get("gathered_parameters", {}),
            refined_query=result.get("refined_query", ""),
            messages=annotated_messages,
            rag_chunks_used=result.get("rag_chunks_used", []),
            confidence=result.get("confidence", "MEDIUM"),
            num_gathering_turns=gathering_turn_count,
            recommendation_summary=result.get("content"),
            recommendation_full_report=result.get("full_report"),
        )

        # Schedule outcome follow-ups at 30, 90, and 180 days
        from datetime import datetime as _dt, timedelta, timezone as _tz
        now = _dt.now(_tz.utc)
        for stage, days in [("30_day", 30), ("90_day", 90), ("180_day", 180)]:
            try:
                scheduled = (now + timedelta(days=days)).isoformat()
                await database.create_followup_schedule(
                    session_id=session_id,
                    followup_stage=stage,
                    scheduled_date=scheduled,
                )
            except Exception as e:
                logger.warning(f"Failed to schedule {stage} follow-up: {e}")

    return {
        "user_message": user_msg,
        "assistant_message": assistant_msg,
        "phase": new_phase,
        "application_domain": result.get("application_domain") or session.get("application_domain"),
    }


@router.post("/api/consult/sessions/{session_id}/messages/stream")
async def send_consult_message_stream(session_id: str, req: ConsultMessageRequest):
    """Stream a consultation response via SSE."""
    session = await database.get_consultation_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Handle force_transition
    is_force_transition = req.force_transition and session["phase"] == "gathering"
    if is_force_transition:
        user_content = (
            "That's all the information I have available. "
            "Please go ahead with your recommendation based on what we've discussed."
        )
    else:
        user_content = strip_html(req.content.strip())
        if not user_content:
            raise HTTPException(status_code=422, detail="Message content is required")

    # Save user message
    user_msg = await database.add_consultation_message(
        session_id=session_id,
        role="user",
        content=user_content,
        phase_at_time=session["phase"],
    )

    # Build conversation history
    conversation_history = [
        {"role": m["role"], "content": m["content"]}
        for m in session["messages"]
    ]

    gathering_turn_count = sum(
        1 for m in session["messages"]
        if m["role"] == "user" and m["phase_at_time"] == "gathering"
    )
    if session["phase"] == "gathering":
        gathering_turn_count += 1

    # Resolve vertical config for this session
    _vc = _resolve_vertical_config(session)

    from core.consultation_engine import generate_consultation_response_stream, generate_session_title

    async def event_generator():
        """SSE event generator."""
        final_result = None

        try:
            for event_type, data in generate_consultation_response_stream(
                session_id=session_id,
                user_message=user_content,
                phase=session["phase"],
                conversation_history=conversation_history,
                gathered_parameters=session.get("gathered_parameters"),
                gathering_turn_count=gathering_turn_count,
                force_transition=is_force_transition,
                vertical_config=_vc,
            ):
                if event_type == "status":
                    yield f"event: status\ndata: {json.dumps({'message': data})}\n\n"
                elif event_type == "metadata":
                    yield f"event: metadata\ndata: {json.dumps(data)}\n\n"
                elif event_type == "text":
                    yield f"event: chunk\ndata: {json.dumps({'text': data})}\n\n"
                elif event_type == "section":
                    yield f"event: section\ndata: {json.dumps({'section': data})}\n\n"
                elif event_type == "done":
                    final_result = data
                elif event_type == "error":
                    yield f"event: error\ndata: {json.dumps({'message': data})}\n\n"
                    return

        except Exception as e:
            logger.error(f"Streaming consultation failed: {e}")
            traceback.print_exc()
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            return

        if not final_result:
            yield f"event: error\ndata: {json.dumps({'message': 'No response generated'})}\n\n"
            return

        # Post-stream: update session, save assistant message, log training data
        new_phase = final_result.get("phase", session["phase"])
        update_kwargs = {}

        if new_phase != session["phase"]:
            update_kwargs["phase"] = new_phase
        if final_result.get("application_domain"):
            update_kwargs["application_domain"] = final_result["application_domain"]
        if final_result.get("gathered_parameters"):
            update_kwargs["gathered_parameters"] = final_result["gathered_parameters"]
        if update_kwargs:
            await database.update_consultation_session(session_id, **update_kwargs)

        assistant_msg = await database.add_consultation_message(
            session_id=session_id,
            role="assistant",
            content=final_result["content"],
            phase_at_time=new_phase,
            rag_chunks_used=final_result.get("rag_chunks_used"),
            full_report=final_result.get("full_report"),
        )

        # Auto-title on first message pair
        if len(session["messages"]) == 0:
            try:
                title = generate_session_title(user_content)
                await database.update_consultation_session(session_id, title=title)
            except Exception:
                pass

        # Log training data on phase transition
        if new_phase == "answering" and session["phase"] == "gathering":
            annotated_messages = [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "phase": m.get("phase_at_time") or "gathering",
                }
                for m in session["messages"]
            ]
            annotated_messages.append(
                {"role": "user", "content": user_content, "phase": "gathering"}
            )
            annotated_messages.append(
                {"role": "assistant", "content": final_result["content"], "phase": "answering"}
            )

            training.log_consultation(
                session_id=session_id,
                application_domain=final_result.get("application_domain", "general"),
                gathered_parameters=final_result.get("gathered_parameters", {}),
                refined_query=final_result.get("refined_query", ""),
                messages=annotated_messages,
                rag_chunks_used=final_result.get("rag_chunks_used", []),
                confidence=final_result.get("confidence", "MEDIUM"),
                num_gathering_turns=gathering_turn_count,
                recommendation_summary=final_result.get("content"),
                recommendation_full_report=final_result.get("full_report"),
            )

            # Schedule follow-ups
            from datetime import datetime as _dt, timedelta, timezone as _tz
            now = _dt.now(_tz.utc)
            for stage, days in [("30_day", 30), ("90_day", 90), ("180_day", 180)]:
                try:
                    scheduled = (now + timedelta(days=days)).isoformat()
                    await database.create_followup_schedule(
                        session_id=session_id,
                        followup_stage=stage,
                        scheduled_date=scheduled,
                    )
                except Exception as e:
                    logger.warning(f"Failed to schedule {stage} follow-up: {e}")

        # Send final complete event with metadata
        complete_data = {
            'phase': new_phase,
            'application_domain': final_result.get('application_domain') or session.get('application_domain'),
        }
        if final_result.get("full_report"):
            complete_data["full_report"] = final_result["full_report"]
        yield f"event: complete\ndata: {json.dumps(complete_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/consult/sessions/{session_id}/feedback")
async def consult_feedback(session_id: str, req: ConsultFeedbackRequest):
    """Submit feedback for a consultation session."""
    session = await database.get_consultation_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Log feedback as training data
    training.log_consultation_feedback(
        session_id=session_id,
        rating=req.rating,
        comment=req.comment,
    )

    return {"status": "ok"}


# ===========================================================================
# Routes: Consultation Outcomes
# ===========================================================================

@router.post("/api/consult/sessions/{session_id}/outcomes")
async def create_consult_outcome(session_id: str, req: ConsultOutcomeRequest):
    """Submit an outcome report for a consultation session."""
    session = await database.get_consultation_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    outcome = await database.create_consultation_outcome(
        session_id=session_id,
        followup_stage=req.followup_stage,
        implementation_status=req.implementation_status,
        performance_rating=req.performance_rating,
        performance_notes=req.performance_notes,
        failure_occurred=req.failure_occurred,
        failure_mode=req.failure_mode,
        failure_timeline=req.failure_timeline,
        operating_conditions_matched=req.operating_conditions_matched,
        operating_conditions_notes=req.operating_conditions_notes,
        modifications_made=req.modifications_made,
        would_recommend_same=req.would_recommend_same,
        alternative_tried=req.alternative_tried,
        additional_notes=req.additional_notes,
    )

    # Extract recommendation summary from last assistant answering-phase message
    recommendation_summary = ""
    for msg in reversed(session.get("messages", [])):
        if msg["role"] == "assistant" and msg.get("phase_at_time") == "answering":
            recommendation_summary = msg["content"][:500]
            break

    # Log to training data
    training.log_consultation_outcome(
        session_id=session_id,
        outcome_id=outcome["id"],
        application_domain=session.get("application_domain") or "general",
        gathered_parameters=session.get("gathered_parameters") or {},
        recommendation_summary=recommendation_summary,
        followup_stage=req.followup_stage,
        implementation_status=req.implementation_status,
        performance_rating=req.performance_rating,
        performance_notes=req.performance_notes,
        failure_occurred=req.failure_occurred,
        failure_mode=req.failure_mode,
        operating_conditions_matched=req.operating_conditions_matched,
        would_recommend_same=req.would_recommend_same,
    )

    return outcome


@router.get("/api/consult/sessions/{session_id}/outcomes")
async def get_consult_outcomes(session_id: str):
    """Get all outcome reports for a consultation session."""
    session = await database.get_consultation_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    outcomes = await database.get_consultation_outcomes(session_id)
    return {"outcomes": outcomes}


@router.put("/api/consult/sessions/{session_id}/outcomes/{outcome_id}")
async def update_consult_outcome(
    session_id: str,
    outcome_id: str,
    req: ConsultOutcomeUpdateRequest,
):
    """Update an existing outcome report."""
    session = await database.get_consultation_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    update_data = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    outcome = await database.update_consultation_outcome(outcome_id, **update_data)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Outcome not found")

    # Log update to training data
    recommendation_summary = ""
    for msg in reversed(session.get("messages", [])):
        if msg["role"] == "assistant" and msg.get("phase_at_time") == "answering":
            recommendation_summary = msg["content"][:500]
            break

    training.log_consultation_outcome(
        session_id=session_id,
        outcome_id=outcome_id,
        application_domain=session.get("application_domain") or "general",
        gathered_parameters=session.get("gathered_parameters") or {},
        recommendation_summary=recommendation_summary,
        followup_stage=outcome.get("followup_stage", "user_initiated"),
        implementation_status=outcome.get("implementation_status"),
        performance_rating=outcome.get("performance_rating"),
        performance_notes=outcome.get("performance_notes"),
        failure_occurred=outcome.get("failure_occurred", False),
        failure_mode=outcome.get("failure_mode"),
        operating_conditions_matched=outcome.get("operating_conditions_matched"),
        would_recommend_same=outcome.get("would_recommend_same"),
    )

    return outcome


@router.get("/api/consult/outcomes/pending-followups")
async def get_pending_followups():
    """List all sessions with scheduled follow-ups that are due (with user email info)."""
    followups = await database.get_pending_followups_with_users()
    return {"followups": followups}


# ===========================================================================
