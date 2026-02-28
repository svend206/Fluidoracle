from __future__ import annotations
"""
Fluidoracle — Questions Routes
"""
import json
import logging
import os
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, StreamingResponse

import core.database as database
from core.models import (
    AskRequest, VoteRequest, CommentRequest,
)

def strip_html(text: str) -> str:
    import re
    return re.sub(r'<[^>]+>', '', text)

def get_client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")

logger = logging.getLogger(__name__)

router = APIRouter()

# Routes: Questions
# ===========================================================================

@router.post("/api/ask")
async def ask_question(req: AskRequest):
    """Submit a question and get an AI-powered expert answer."""
    question_text = strip_html(req.question.strip())

    # Check for duplicate question (skip if the cached answer was a failure)
    existing = await database.get_questions(page=1, limit=100)
    for q in existing:
        if q["question"].lower().strip() == question_text.lower().strip():
            # Don't return cached failures
            if "declined to answer" in q["answer"] or "unable to generate" in q["answer"]:
                continue
            return q  # Return existing answer instead of re-generating

    # Generate answer (this is slow — RAG retrieval + Claude API call)
    # Import here to avoid loading heavy ML models at startup
    from core.answer_engine import generate_answer

    try:
        result = generate_answer(question_text)
    except Exception as e:
        logger.error(f"Answer generation failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Answer generation failed: {e}")

    # Save to database
    question_id = str(uuid.uuid4())
    saved = await database.save_question(
        id=question_id,
        question=question_text,
        answer=result["answer"],
        confidence=result["confidence"],
        sources=result["sources"],
        warnings=result["warnings"],
    )

    # Log as training data (fire-and-forget, never fails the request)
    training.log_answered_question(
        question=question_text,
        answer=result["answer"],
        confidence=result["confidence"],
        sources=result["sources"],
        question_id=question_id,
    )

    return saved


@router.post("/api/ask/stream")
async def ask_question_stream(req: AskRequest):
    """Submit a question and stream the expert answer via SSE."""
    import json as _json

    question_text = strip_html(req.question.strip())

    # Check for duplicate question (return cached answer as instant SSE)
    existing = await database.get_questions(page=1, limit=100)
    for q in existing:
        if q["question"].lower().strip() == question_text.lower().strip():
            if "declined to answer" in q["answer"] or "unable to generate" in q["answer"]:
                continue

            # Return cached answer as an instant SSE stream
            def _cached_stream():
                yield f"event: status\ndata: {_json.dumps({'stage': 'generating', 'confidence': q.get('confidence', 'MEDIUM'), 'sources': q.get('sources', []), 'warnings': q.get('warnings', [])})}\n\n"
                yield f"event: chunk\ndata: {_json.dumps({'text': q['answer']})}\n\n"
                yield f"event: complete\ndata: {_json.dumps({'answer': q['answer'], 'confidence': q.get('confidence', 'MEDIUM'), 'sources': q.get('sources', []), 'warnings': q.get('warnings', []), 'question_id': q['id']})}\n\n"

            return StreamingResponse(
                _cached_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

    # Stream a fresh answer
    from core.answer_engine import generate_answer_stream

    def _streaming_wrapper():
        """Wrap the generator to capture the final answer and save to DB after streaming."""
        final_data = {}
        for event in generate_answer_stream(question_text):
            yield event
            # Capture the complete event data for DB save
            if event.startswith("event: complete"):
                data_line = event.split("data: ", 1)[1].strip()
                final_data = _json.loads(data_line)

        # After streaming is done, save to DB and send the question_id
        if final_data.get("answer"):
            import asyncio
            question_id = str(uuid.uuid4())

            # Run the async DB save in a new event loop (we're in a sync generator)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(database.save_question(
                    id=question_id,
                    question=question_text,
                    answer=final_data["answer"],
                    confidence=final_data.get("confidence", "MEDIUM"),
                    sources=final_data.get("sources", []),
                    warnings=final_data.get("warnings", []),
                ))
            except Exception as e:
                logger.error(f"[stream] DB save failed: {e}")
            finally:
                loop.close()

            # Log training data
            training.log_answered_question(
                question=question_text,
                answer=final_data["answer"],
                confidence=final_data.get("confidence", "MEDIUM"),
                sources=final_data.get("sources", []),
                question_id=question_id,
            )

            # Send final event with question_id so frontend can enable voting
            yield f"event: saved\ndata: {_json.dumps({'question_id': question_id})}\n\n"

    return StreamingResponse(
        _streaming_wrapper(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/questions")
async def list_questions(page: int = 1, limit: int = 20):
    """List recent questions with answers."""
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 20

    questions = await database.get_questions(page=page, limit=limit)
    return {"questions": questions, "page": page, "limit": limit}


@router.get("/api/questions/{question_id}")
async def get_question(question_id: str):
    """Get a single question with full details."""
    question = await database.get_question(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


# ===========================================================================
# Routes: Votes
# ===========================================================================

@router.post("/api/questions/{question_id}/vote")
async def vote(question_id: str, req: VoteRequest, request: Request):
    """Vote on a question's answer."""
    # Verify question exists
    question = await database.get_question(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    voter_ip = get_client_ip(request)
    result = await database.add_vote(question_id, req.direction, voter_ip)

    # If upvotes cross the threshold (3+), log as high-quality training data
    if req.direction == "up" and result["vote_up"] >= 3:
        training.log_upvoted_question(
            question=question["question"],
            answer=question["answer"],
            confidence=question["confidence"],
            sources=question["sources"],
            upvote_count=result["vote_up"],
            question_id=question_id,
        )

    # If downvotes cross the threshold (2+), log as low-quality training signal
    if req.direction == "down" and result["vote_down"] >= 2:
        training.log_downvoted_question(
            question=question["question"],
            answer=question["answer"],
            confidence=question["confidence"],
            sources=question["sources"],
            downvote_count=result["vote_down"],
            question_id=question_id,
        )

    return result


# ===========================================================================
# Routes: Comments
# ===========================================================================

@router.post("/api/questions/{question_id}/comments")
async def create_comment(question_id: str, req: CommentRequest):
    """Add a comment or correction to a question."""
    # Verify question exists
    question = await database.get_question(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    body = strip_html(req.body.strip())
    author = strip_html(req.author_name.strip()) or "Anonymous"

    comment = await database.add_comment(
        question_id=question_id,
        body=body,
        is_correction=req.is_correction,
        author_name=author,
    )

    # If it's a correction, also log to training pipeline
    if req.is_correction:
        training.log_user_correction(
            question=question["question"],
            original_answer=question["answer"],
            correction_text=body,
            question_id=question_id,
        )

    return comment


@router.get("/api/questions/{question_id}/comments")
async def list_comments(question_id: str):
    """Get all comments for a question."""
    comments = await database.get_comments(question_id)
    return {"comments": comments}


# ===========================================================================
# Routes: Stats
# ===========================================================================

@router.get("/api/stats")
async def stats():
    """Platform and training data statistics."""
    db_stats = await database.get_stats()
    training_stats = training.get_training_stats()

    return {
        "platform": db_stats,
        "training_data": training_stats,
    }


# ===========================================================================
