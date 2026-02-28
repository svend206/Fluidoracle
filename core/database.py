from __future__ import annotations
"""
Hydraulic Filter Platform — Database Layer
=======================================
Async SQLite database for community data: questions, votes, comments.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

# ---------------------------------------------------------------------------
# Database path (set by main.py at startup)
# ---------------------------------------------------------------------------
_db_path: str = ""


def set_db_path(path: str):
    global _db_path
    _db_path = path


def _get_db_path() -> str:
    if not _db_path:
        raise RuntimeError("Database path not set. Call set_db_path() first.")
    return _db_path


# ===========================================================================
# Initialization
# ===========================================================================

async def init_db():
    """Create tables if they don't exist."""
    Path(_get_db_path()).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                confidence TEXT NOT NULL,
                sources TEXT,
                warnings TEXT,
                vote_up INTEGER DEFAULT 0,
                vote_down INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL REFERENCES questions(id),
                body TEXT NOT NULL,
                is_correction BOOLEAN DEFAULT FALSE,
                author_name TEXT DEFAULT 'Anonymous',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id TEXT PRIMARY KEY,
                question_id TEXT NOT NULL REFERENCES questions(id),
                direction TEXT NOT NULL,
                voter_ip TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(question_id, voter_ip)
            )
        """)

        # --- Invention Sessions ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invention_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS invention_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES invention_sessions(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources TEXT,
                confidence TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- Consultation Sessions ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS consultation_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New Consultation',
                phase TEXT NOT NULL DEFAULT 'gathering',
                application_domain TEXT,
                gathered_parameters TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS consultation_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES consultation_sessions(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                phase_at_time TEXT,
                rag_chunks_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- Consultation Outcomes ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS consultation_outcomes (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES consultation_sessions(id),
                followup_stage TEXT NOT NULL,
                implementation_status TEXT,
                performance_rating INTEGER,
                performance_notes TEXT,
                failure_occurred BOOLEAN DEFAULT FALSE,
                failure_mode TEXT,
                failure_timeline TEXT,
                operating_conditions_matched BOOLEAN,
                operating_conditions_notes TEXT,
                modifications_made TEXT,
                would_recommend_same BOOLEAN,
                alternative_tried TEXT,
                additional_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS outcome_followup_schedule (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES consultation_sessions(id),
                followup_stage TEXT NOT NULL,
                scheduled_date TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'pending',
                sent_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- Consultation Email Subscribers (legacy — kept for data, no longer written to) ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS consultation_subscribers (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES consultation_sessions(id),
                email TEXT NOT NULL,
                application_domain TEXT,
                topics TEXT,
                verification_token TEXT NOT NULL,
                unsubscribe_token TEXT NOT NULL,
                verified BOOLEAN DEFAULT FALSE,
                verified_at TIMESTAMP,
                unsubscribed BOOLEAN DEFAULT FALSE,
                unsubscribed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- Knowledge Base Updates (for topic matching) ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_base_updates (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                domains TEXT,
                topics TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- Users (passwordless auth) ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                email_verified BOOLEAN DEFAULT FALSE,
                topic_subscription BOOLEAN DEFAULT TRUE,
                feature_updates BOOLEAN DEFAULT FALSE,
                unsubscribe_token TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP
            )
        """)

        # --- Auth Codes (passwordless login) ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auth_codes (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- Auth Sessions (bearer tokens) ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """)

        # --- Add user_id to consultation_sessions (migration-safe) ---
        try:
            await db.execute(
                "ALTER TABLE consultation_sessions ADD COLUMN user_id TEXT REFERENCES users(id)"
            )
        except Exception:
            pass  # Column already exists

        # --- Add full_report to consultation_messages (migration-safe) ---
        try:
            await db.execute(
                "ALTER TABLE consultation_messages ADD COLUMN full_report TEXT"
            )
        except Exception:
            pass  # Column already exists

        # --- Add vertical_id and platform_id to consultation_sessions (migration-safe) ---
        try:
            await db.execute(
                "ALTER TABLE consultation_sessions ADD COLUMN vertical_id TEXT"
            )
        except Exception:
            pass  # Column already exists
        try:
            await db.execute(
                "ALTER TABLE consultation_sessions ADD COLUMN platform_id TEXT"
            )
        except Exception:
            pass  # Column already exists

        # --- Add vertical_id to questions for Q&A tagging (migration-safe) ---
        try:
            await db.execute(
                "ALTER TABLE questions ADD COLUMN vertical_id TEXT"
            )
        except Exception:
            pass  # Column already exists

        # --- Off-vertical demand signal table ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS off_vertical_demand (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                source_vertical TEXT,
                source_platform TEXT,
                detected_target_vertical TEXT,
                query_text TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                vertical_id TEXT,
                platform_id TEXT,
                phase TEXT,
                model TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                estimated_cost_usd REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()


# ===========================================================================
# LLM Usage Tracking
# ===========================================================================

# Approximate costs per 1M tokens (USD) — update when pricing changes
_MODEL_COSTS = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-haiku-3-5-20241022": {"input": 0.80, "output": 4.0},
}


async def log_llm_usage(
    response_usage,
    model: str,
    phase: str,
    session_id: str | None = None,
    vertical_id: str | None = None,
    platform_id: str | None = None,
) -> None:
    """Persist a single LLM call's token usage. Call after every Anthropic API response.

    Args:
        response_usage: The ``response.usage`` object from the Anthropic SDK.
        model: Model identifier string.
        phase: One of 'gathering', 'answering', 'followup', 'question', 'invention', 'other'.
    """
    input_tokens = getattr(response_usage, "input_tokens", 0)
    output_tokens = getattr(response_usage, "output_tokens", 0)

    costs = _MODEL_COSTS.get(model, {"input": 3.0, "output": 15.0})
    estimated_cost = (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000

    try:
        async with aiosqlite.connect(_get_db_path()) as db:
            await db.execute(
                """INSERT INTO llm_usage
                   (session_id, vertical_id, platform_id, phase, model,
                    input_tokens, output_tokens, estimated_cost_usd)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, vertical_id, platform_id, phase, model,
                 input_tokens, output_tokens, estimated_cost),
            )
            await db.commit()
    except Exception:
        pass  # Non-critical — don't break the request over telemetry


def log_llm_usage_sync(
    response_usage,
    model: str,
    phase: str,
    session_id: str | None = None,
    vertical_id: str | None = None,
    platform_id: str | None = None,
) -> None:
    """Synchronous version for use in sync engine code (consultation/answer/invention)."""
    import sqlite3

    input_tokens = getattr(response_usage, "input_tokens", 0)
    output_tokens = getattr(response_usage, "output_tokens", 0)

    costs = _MODEL_COSTS.get(model, {"input": 3.0, "output": 15.0})
    estimated_cost = (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000

    try:
        conn = sqlite3.connect(_get_db_path())
        conn.execute(
            """INSERT INTO llm_usage
               (session_id, vertical_id, platform_id, phase, model,
                input_tokens, output_tokens, estimated_cost_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, vertical_id, platform_id, phase, model,
             input_tokens, output_tokens, estimated_cost),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ===========================================================================
# Questions
# ===========================================================================

async def save_question(
    id: str,
    question: str,
    answer: str,
    confidence: str,
    sources: list[str],
    warnings: list[str],
) -> dict:
    """Insert a new question/answer record."""
    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO questions (id, question, answer, confidence, sources, warnings)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (id, question, answer, confidence, json.dumps(sources), json.dumps(warnings)),
        )
        await db.commit()

    return {
        "id": id,
        "question": question,
        "answer": answer,
        "confidence": confidence,
        "sources": sources,
        "warnings": warnings,
        "vote_up": 0,
        "vote_down": 0,
    }


async def get_questions(page: int = 1, limit: int = 20) -> list[dict]:
    """Get paginated list of questions, most recent first."""
    offset = (page - 1) * limit

    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                q.*,
                (SELECT COUNT(*) FROM comments c WHERE c.question_id = q.id) as comment_count
            FROM questions q
            ORDER BY q.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "question": row["question"],
            "answer": row["answer"],
            "confidence": row["confidence"],
            "sources": json.loads(row["sources"]) if row["sources"] else [],
            "warnings": json.loads(row["warnings"]) if row["warnings"] else [],
            "vote_up": row["vote_up"],
            "vote_down": row["vote_down"],
            "comment_count": row["comment_count"],
            "created_at": row["created_at"],
        })

    return results


async def get_question(id: str) -> dict | None:
    """Get a single question with full details."""
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                q.*,
                (SELECT COUNT(*) FROM comments c WHERE c.question_id = q.id) as comment_count
            FROM questions q
            WHERE q.id = ?
            """,
            (id,),
        )
        row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "confidence": row["confidence"],
        "sources": json.loads(row["sources"]) if row["sources"] else [],
        "warnings": json.loads(row["warnings"]) if row["warnings"] else [],
        "vote_up": row["vote_up"],
        "vote_down": row["vote_down"],
        "comment_count": row["comment_count"],
        "created_at": row["created_at"],
    }


# ===========================================================================
# Delete question
# ===========================================================================

async def delete_question(question_id: str) -> bool:
    """Delete a question and all its associated votes and comments."""
    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute("DELETE FROM comments WHERE question_id = ?", (question_id,))
        await db.execute("DELETE FROM votes WHERE question_id = ?", (question_id,))
        cursor = await db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        await db.commit()
        return cursor.rowcount > 0


# ===========================================================================
# Votes
# ===========================================================================

async def add_vote(question_id: str, direction: str, voter_ip: str) -> dict:
    """Add or update a vote. One vote per IP per question."""
    vote_id = str(uuid.uuid4())

    async with aiosqlite.connect(_get_db_path()) as db:
        # Check for existing vote from this IP
        cursor = await db.execute(
            "SELECT id, direction FROM votes WHERE question_id = ? AND voter_ip = ?",
            (question_id, voter_ip),
        )
        existing = await cursor.fetchone()

        if existing:
            old_direction = existing[1]
            if old_direction == direction:
                # Same vote again — remove it (toggle off)
                await db.execute("DELETE FROM votes WHERE id = ?", (existing[0],))
                col = "vote_up" if direction == "up" else "vote_down"
                await db.execute(
                    f"UPDATE questions SET {col} = MAX(0, {col} - 1) WHERE id = ?",
                    (question_id,),
                )
            else:
                # Change vote direction
                await db.execute(
                    "UPDATE votes SET direction = ?, id = ? WHERE question_id = ? AND voter_ip = ?",
                    (direction, vote_id, question_id, voter_ip),
                )
                # Decrement old, increment new
                old_col = "vote_up" if old_direction == "up" else "vote_down"
                new_col = "vote_up" if direction == "up" else "vote_down"
                await db.execute(
                    f"UPDATE questions SET {old_col} = MAX(0, {old_col} - 1), {new_col} = {new_col} + 1 WHERE id = ?",
                    (question_id,),
                )
        else:
            # New vote
            await db.execute(
                "INSERT INTO votes (id, question_id, direction, voter_ip) VALUES (?, ?, ?, ?)",
                (vote_id, question_id, direction, voter_ip),
            )
            col = "vote_up" if direction == "up" else "vote_down"
            await db.execute(
                f"UPDATE questions SET {col} = {col} + 1 WHERE id = ?",
                (question_id,),
            )

        await db.commit()

        # Return updated vote counts
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT vote_up, vote_down FROM questions WHERE id = ?",
            (question_id,),
        )
        row = await cursor.fetchone()

    return {
        "question_id": question_id,
        "vote_up": row["vote_up"] if row else 0,
        "vote_down": row["vote_down"] if row else 0,
    }


# ===========================================================================
# Comments
# ===========================================================================

async def add_comment(
    question_id: str,
    body: str,
    is_correction: bool = False,
    author_name: str = "Anonymous",
) -> dict:
    """Add a comment to a question."""
    comment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO comments (id, question_id, body, is_correction, author_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (comment_id, question_id, body, is_correction, author_name, now),
        )
        await db.commit()

    return {
        "id": comment_id,
        "question_id": question_id,
        "body": body,
        "is_correction": is_correction,
        "author_name": author_name,
        "created_at": now,
    }


async def get_comments(question_id: str) -> list[dict]:
    """Get all comments for a question, oldest first."""
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM comments
            WHERE question_id = ?
            ORDER BY created_at ASC
            """,
            (question_id,),
        )
        rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "question_id": row["question_id"],
            "body": row["body"],
            "is_correction": bool(row["is_correction"]),
            "author_name": row["author_name"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


# ===========================================================================
# Stats
# ===========================================================================

async def get_stats() -> dict:
    """Get basic platform statistics."""
    async with aiosqlite.connect(_get_db_path()) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM questions")
        question_count = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM comments")
        comment_count = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM votes")
        vote_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM comments WHERE is_correction = TRUE"
        )
        correction_count = (await cursor.fetchone())[0]

    return {
        "questions": question_count,
        "comments": comment_count,
        "votes": vote_count,
        "corrections": correction_count,
    }


# ===========================================================================
# Invention Sessions
# ===========================================================================

async def create_invention_session(title: str = "New Session") -> dict:
    """Create a new invention session."""
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO invention_sessions (id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, title, now, now),
        )
        await db.commit()

    return {
        "id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
    }


async def get_invention_sessions() -> list[dict]:
    """List all invention sessions, newest first."""
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                s.*,
                (SELECT COUNT(*) FROM invention_messages m WHERE m.session_id = s.id) as message_count
            FROM invention_sessions s
            ORDER BY s.updated_at DESC
            """
        )
        rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"],
        }
        for row in rows
    ]


async def get_invention_session(session_id: str) -> dict | None:
    """Get a single invention session with all its messages."""
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        # Get session
        cursor = await db.execute(
            "SELECT * FROM invention_sessions WHERE id = ?",
            (session_id,),
        )
        session_row = await cursor.fetchone()
        if session_row is None:
            return None

        # Get messages
        cursor = await db.execute(
            """
            SELECT * FROM invention_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        message_rows = await cursor.fetchall()

    messages = [
        {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "sources": json.loads(row["sources"]) if row["sources"] else None,
            "confidence": row["confidence"],
            "created_at": row["created_at"],
        }
        for row in message_rows
    ]

    return {
        "id": session_row["id"],
        "title": session_row["title"],
        "created_at": session_row["created_at"],
        "updated_at": session_row["updated_at"],
        "messages": messages,
    }


async def delete_invention_session(session_id: str) -> bool:
    """Delete an invention session and all its messages."""
    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            "DELETE FROM invention_messages WHERE session_id = ?",
            (session_id,),
        )
        cursor = await db.execute(
            "DELETE FROM invention_sessions WHERE id = ?",
            (session_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def add_invention_message(
    session_id: str,
    role: str,
    content: str,
    sources: list[str] | None = None,
    confidence: str | None = None,
) -> dict:
    """Add a message to an invention session."""
    message_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO invention_messages (id, session_id, role, content, sources, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                role,
                content,
                json.dumps(sources) if sources else None,
                confidence,
                now,
            ),
        )
        # Update session's updated_at timestamp
        await db.execute(
            "UPDATE invention_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        await db.commit()

    return {
        "id": message_id,
        "role": role,
        "content": content,
        "sources": sources,
        "confidence": confidence,
        "created_at": now,
    }


async def update_invention_session_title(session_id: str, title: str) -> bool:
    """Update the title of an invention session."""
    async with aiosqlite.connect(_get_db_path()) as db:
        cursor = await db.execute(
            "UPDATE invention_sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )
        await db.commit()
        return cursor.rowcount > 0


# ===========================================================================
# Consultation Sessions
# ===========================================================================

async def create_consultation_session(
    title: str = "New Consultation",
    vertical_id: str | None = None,
    platform_id: str | None = None,
) -> dict:
    """Create a new consultation session."""
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO consultation_sessions
                (id, title, phase, vertical_id, platform_id, created_at, updated_at)
            VALUES (?, ?, 'gathering', ?, ?, ?, ?)
            """,
            (session_id, title, vertical_id, platform_id, now, now),
        )
        await db.commit()

    return {
        "id": session_id,
        "title": title,
        "phase": "gathering",
        "application_domain": None,
        "gathered_parameters": None,
        "vertical_id": vertical_id,
        "platform_id": platform_id,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
    }


async def get_consultation_sessions() -> list[dict]:
    """List all consultation sessions, newest first."""
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                s.*,
                (SELECT COUNT(*) FROM consultation_messages m WHERE m.session_id = s.id) as message_count
            FROM consultation_sessions s
            ORDER BY s.updated_at DESC
            """
        )
        rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "phase": row["phase"],
            "application_domain": row["application_domain"],
            "gathered_parameters": json.loads(row["gathered_parameters"]) if row["gathered_parameters"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"],
        }
        for row in rows
    ]


async def get_consultation_session(session_id: str) -> dict | None:
    """Get a single consultation session with all its messages."""
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT * FROM consultation_sessions WHERE id = ?",
            (session_id,),
        )
        session_row = await cursor.fetchone()
        if session_row is None:
            return None

        cursor = await db.execute(
            """
            SELECT * FROM consultation_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        message_rows = await cursor.fetchall()

    messages = [
        {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "phase_at_time": row["phase_at_time"],
            "rag_chunks_used": json.loads(row["rag_chunks_used"]) if row["rag_chunks_used"] else None,
            "full_report": row["full_report"] if "full_report" in row.keys() else None,
            "created_at": row["created_at"],
        }
        for row in message_rows
    ]

    return {
        "id": session_row["id"],
        "title": session_row["title"],
        "phase": session_row["phase"],
        "application_domain": session_row["application_domain"],
        "gathered_parameters": json.loads(session_row["gathered_parameters"]) if session_row["gathered_parameters"] else None,
        "created_at": session_row["created_at"],
        "updated_at": session_row["updated_at"],
        "messages": messages,
    }


async def delete_consultation_session(session_id: str) -> bool:
    """Delete a consultation session and all its messages."""
    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            "DELETE FROM consultation_messages WHERE session_id = ?",
            (session_id,),
        )
        cursor = await db.execute(
            "DELETE FROM consultation_sessions WHERE id = ?",
            (session_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def add_consultation_message(
    session_id: str,
    role: str,
    content: str,
    phase_at_time: str | None = None,
    rag_chunks_used: list[str] | None = None,
    full_report: str | None = None,
) -> dict:
    """Add a message to a consultation session."""
    message_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO consultation_messages
                (id, session_id, role, content, phase_at_time, rag_chunks_used, full_report, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                role,
                content,
                phase_at_time,
                json.dumps(rag_chunks_used) if rag_chunks_used else None,
                full_report,
                now,
            ),
        )
        await db.execute(
            "UPDATE consultation_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        await db.commit()

    return {
        "id": message_id,
        "role": role,
        "content": content,
        "phase_at_time": phase_at_time,
        "rag_chunks_used": rag_chunks_used,
        "full_report": full_report,
        "created_at": now,
    }


# ===========================================================================
# Consultation Outcomes
# ===========================================================================

async def create_consultation_outcome(
    session_id: str,
    followup_stage: str,
    implementation_status: str | None = None,
    performance_rating: int | None = None,
    performance_notes: str | None = None,
    failure_occurred: bool = False,
    failure_mode: str | None = None,
    failure_timeline: str | None = None,
    operating_conditions_matched: bool | None = None,
    operating_conditions_notes: str | None = None,
    modifications_made: str | None = None,
    would_recommend_same: bool | None = None,
    alternative_tried: str | None = None,
    additional_notes: str | None = None,
) -> dict:
    """Create an outcome report for a consultation session."""
    outcome_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO consultation_outcomes
                (id, session_id, followup_stage, implementation_status,
                 performance_rating, performance_notes, failure_occurred,
                 failure_mode, failure_timeline, operating_conditions_matched,
                 operating_conditions_notes, modifications_made,
                 would_recommend_same, alternative_tried, additional_notes,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome_id, session_id, followup_stage, implementation_status,
                performance_rating, performance_notes, failure_occurred,
                failure_mode, failure_timeline, operating_conditions_matched,
                operating_conditions_notes, modifications_made,
                would_recommend_same, alternative_tried, additional_notes,
                now, now,
            ),
        )
        # Update session timestamp
        await db.execute(
            "UPDATE consultation_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        await db.commit()

    return {
        "id": outcome_id,
        "session_id": session_id,
        "followup_stage": followup_stage,
        "implementation_status": implementation_status,
        "performance_rating": performance_rating,
        "performance_notes": performance_notes,
        "failure_occurred": failure_occurred,
        "failure_mode": failure_mode,
        "failure_timeline": failure_timeline,
        "operating_conditions_matched": operating_conditions_matched,
        "operating_conditions_notes": operating_conditions_notes,
        "modifications_made": modifications_made,
        "would_recommend_same": would_recommend_same,
        "alternative_tried": alternative_tried,
        "additional_notes": additional_notes,
        "created_at": now,
        "updated_at": now,
    }


async def get_consultation_outcomes(session_id: str) -> list[dict]:
    """Get all outcome reports for a consultation session, oldest first."""
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM consultation_outcomes
            WHERE session_id = ?
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
        rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "session_id": row["session_id"],
            "followup_stage": row["followup_stage"],
            "implementation_status": row["implementation_status"],
            "performance_rating": row["performance_rating"],
            "performance_notes": row["performance_notes"],
            "failure_occurred": bool(row["failure_occurred"]),
            "failure_mode": row["failure_mode"],
            "failure_timeline": row["failure_timeline"],
            "operating_conditions_matched": row["operating_conditions_matched"] if row["operating_conditions_matched"] is None else bool(row["operating_conditions_matched"]),
            "operating_conditions_notes": row["operating_conditions_notes"],
            "modifications_made": row["modifications_made"],
            "would_recommend_same": row["would_recommend_same"] if row["would_recommend_same"] is None else bool(row["would_recommend_same"]),
            "alternative_tried": row["alternative_tried"],
            "additional_notes": row["additional_notes"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


async def update_consultation_outcome(
    outcome_id: str,
    **kwargs,
) -> dict | None:
    """Update an existing outcome report. Returns updated outcome or None."""
    allowed_fields = {
        "followup_stage", "implementation_status", "performance_rating",
        "performance_notes", "failure_occurred", "failure_mode",
        "failure_timeline", "operating_conditions_matched",
        "operating_conditions_notes", "modifications_made",
        "would_recommend_same", "alternative_tried", "additional_notes",
    }

    updates = []
    params = []
    for key, value in kwargs.items():
        if key in allowed_fields:
            updates.append(f"{key} = ?")
            params.append(value)

    if not updates:
        return None

    now = datetime.now(timezone.utc).isoformat()
    updates.append("updated_at = ?")
    params.append(now)
    params.append(outcome_id)

    async with aiosqlite.connect(_get_db_path()) as db:
        cursor = await db.execute(
            f"UPDATE consultation_outcomes SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.commit()

        if cursor.rowcount == 0:
            return None

        # Return the updated record
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM consultation_outcomes WHERE id = ?",
            (outcome_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "followup_stage": row["followup_stage"],
        "implementation_status": row["implementation_status"],
        "performance_rating": row["performance_rating"],
        "performance_notes": row["performance_notes"],
        "failure_occurred": bool(row["failure_occurred"]),
        "failure_mode": row["failure_mode"],
        "failure_timeline": row["failure_timeline"],
        "operating_conditions_matched": row["operating_conditions_matched"] if row["operating_conditions_matched"] is None else bool(row["operating_conditions_matched"]),
        "operating_conditions_notes": row["operating_conditions_notes"],
        "modifications_made": row["modifications_made"],
        "would_recommend_same": row["would_recommend_same"] if row["would_recommend_same"] is None else bool(row["would_recommend_same"]),
        "alternative_tried": row["alternative_tried"],
        "additional_notes": row["additional_notes"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ===========================================================================
# Outcome Follow-up Scheduling
# ===========================================================================

async def create_followup_schedule(
    session_id: str,
    followup_stage: str,
    scheduled_date: str,
) -> dict:
    """Create a follow-up schedule entry."""
    schedule_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO outcome_followup_schedule
                (id, session_id, followup_stage, scheduled_date, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (schedule_id, session_id, followup_stage, scheduled_date, now),
        )
        await db.commit()

    return {
        "id": schedule_id,
        "session_id": session_id,
        "followup_stage": followup_stage,
        "scheduled_date": scheduled_date,
        "status": "pending",
        "created_at": now,
    }


async def get_pending_followups() -> list[dict]:
    """Get all follow-ups that are due (scheduled_date <= now AND status = 'pending')."""
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT f.*, s.title as session_title, s.application_domain
            FROM outcome_followup_schedule f
            JOIN consultation_sessions s ON f.session_id = s.id
            WHERE f.scheduled_date <= ? AND f.status = 'pending'
            ORDER BY f.scheduled_date ASC
            """,
            (now,),
        )
        rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "session_id": row["session_id"],
            "session_title": row["session_title"],
            "application_domain": row["application_domain"],
            "followup_stage": row["followup_stage"],
            "scheduled_date": row["scheduled_date"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


async def update_consultation_session(
    session_id: str,
    title: str | None = None,
    phase: str | None = None,
    application_domain: str | None = None,
    gathered_parameters: dict | None = None,
    user_id: str | None = None,
) -> bool:
    """Update consultation session metadata."""
    updates = []
    params = []

    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if phase is not None:
        updates.append("phase = ?")
        params.append(phase)
    if application_domain is not None:
        updates.append("application_domain = ?")
        params.append(application_domain)
    if gathered_parameters is not None:
        updates.append("gathered_parameters = ?")
        params.append(json.dumps(gathered_parameters))
    if user_id is not None:
        updates.append("user_id = ?")
        params.append(user_id)

    if not updates:
        return False

    updates.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(session_id)

    async with aiosqlite.connect(_get_db_path()) as db:
        cursor = await db.execute(
            f"UPDATE consultation_sessions SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.commit()
        return cursor.rowcount > 0


# ===========================================================================
# Users & Authentication
# ===========================================================================

async def get_or_create_user(email: str, unsubscribe_token: str) -> dict:
    """Get an existing user or create a new one by email."""
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        )
        row = await cursor.fetchone()

        if row:
            return {
                "id": row["id"],
                "email": row["email"],
                "email_verified": bool(row["email_verified"]),
                "topic_subscription": bool(row["topic_subscription"]),
                "feature_updates": bool(row["feature_updates"]),
                "created_at": row["created_at"],
            }

        # Create new user
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            """
            INSERT INTO users (id, email, unsubscribe_token, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, email, unsubscribe_token, now),
        )
        await db.commit()

    return {
        "id": user_id,
        "email": email,
        "email_verified": False,
        "topic_subscription": True,
        "feature_updates": False,
        "created_at": now,
    }


async def create_auth_code(email: str, code: str, expires_at: str) -> dict:
    """Store a 6-digit auth code for passwordless login."""
    code_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO auth_codes (id, email, code, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (code_id, email, code, expires_at, now),
        )
        await db.commit()

    return {"id": code_id, "email": email, "expires_at": expires_at}


async def verify_auth_code(email: str, code: str) -> bool:
    """Check if a valid, unused, unexpired auth code exists for this email."""
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        cursor = await db.execute(
            """
            SELECT id FROM auth_codes
            WHERE email = ? AND code = ? AND used = FALSE AND expires_at > ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (email, code, now),
        )
        row = await cursor.fetchone()

        if row is None:
            return False

        # Mark code as used
        await db.execute(
            "UPDATE auth_codes SET used = TRUE WHERE id = ?", (row[0],)
        )

        # Mark user as verified and update last_login
        await db.execute(
            "UPDATE users SET email_verified = TRUE, last_login_at = ? WHERE email = ?",
            (now, email),
        )
        await db.commit()

    return True


async def count_recent_auth_codes(email: str, since: str) -> int:
    """Count auth codes sent to an email since a given timestamp (rate limiting)."""
    async with aiosqlite.connect(_get_db_path()) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM auth_codes WHERE email = ? AND created_at > ?",
            (email, since),
        )
        return (await cursor.fetchone())[0]


async def create_auth_session(user_id: str, expires_at: str) -> str:
    """Create a bearer-token session. Returns the token (which is the row ID)."""
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO auth_sessions (id, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, user_id, now, expires_at),
        )
        await db.commit()

    return token


async def get_user_by_token(token: str) -> dict | None:
    """Look up a user by their session token. Returns None if invalid/expired."""
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT u.* FROM auth_sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ? AND s.expires_at > ?
            """,
            (token, now),
        )
        row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "email": row["email"],
        "email_verified": bool(row["email_verified"]),
        "topic_subscription": bool(row["topic_subscription"]),
        "feature_updates": bool(row["feature_updates"]),
        "unsubscribe_token": row["unsubscribe_token"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


async def delete_auth_session(token: str) -> bool:
    """Delete a session token (logout)."""
    async with aiosqlite.connect(_get_db_path()) as db:
        cursor = await db.execute(
            "DELETE FROM auth_sessions WHERE id = ?", (token,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_user_by_email(email: str) -> dict | None:
    """Look up a user by email."""
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        )
        row = await cursor.fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "email": row["email"],
        "email_verified": bool(row["email_verified"]),
        "topic_subscription": bool(row["topic_subscription"]),
        "feature_updates": bool(row["feature_updates"]),
        "unsubscribe_token": row["unsubscribe_token"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


async def unsubscribe_user(unsubscribe_token: str) -> dict | None:
    """Unsubscribe a user via their unsubscribe token."""
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE unsubscribe_token = ?",
            (unsubscribe_token,),
        )
        row = await cursor.fetchone()

        if row is None:
            return None

        await db.execute(
            "UPDATE users SET topic_subscription = FALSE, feature_updates = FALSE WHERE id = ?",
            (row["id"],),
        )
        await db.commit()

    return {"id": row["id"], "email": row["email"]}


# ===========================================================================
# Session Claiming (link anonymous sessions to authenticated user)
# ===========================================================================

async def claim_sessions(user_id: str, session_ids: list[str]) -> int:
    """Claim anonymous consultation sessions for an authenticated user.

    Only claims sessions where user_id IS NULL (don't steal other users' sessions).
    Returns count of sessions claimed.
    """
    if not session_ids:
        return 0

    claimed = 0
    async with aiosqlite.connect(_get_db_path()) as db:
        for sid in session_ids:
            cursor = await db.execute(
                "UPDATE consultation_sessions SET user_id = ? WHERE id = ? AND user_id IS NULL",
                (user_id, sid),
            )
            claimed += cursor.rowcount
        await db.commit()

    return claimed


async def get_user_consultation_sessions(user_id: str) -> list[dict]:
    """Get all consultation sessions belonging to a user."""
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                s.*,
                (SELECT COUNT(*) FROM consultation_messages m WHERE m.session_id = s.id) as message_count
            FROM consultation_sessions s
            WHERE s.user_id = ?
            ORDER BY s.updated_at DESC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "phase": row["phase"],
            "application_domain": row["application_domain"],
            "gathered_parameters": json.loads(row["gathered_parameters"]) if row["gathered_parameters"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": row["message_count"],
        }
        for row in rows
    ]


# ===========================================================================
# Knowledge Base Updates
# ===========================================================================

async def create_knowledge_update(
    title: str,
    description: str,
    domains: list[str] | None = None,
    topics: list[str] | None = None,
) -> dict:
    """Record a knowledge base update for subscriber notifications."""
    update_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        await db.execute(
            """
            INSERT INTO knowledge_base_updates (id, title, description, domains, topics, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                update_id, title, description,
                json.dumps(domains) if domains else None,
                json.dumps(topics) if topics else None,
                now,
            ),
        )
        await db.commit()

    return {
        "id": update_id,
        "title": title,
        "description": description,
        "domains": domains,
        "topics": topics,
        "created_at": now,
    }


async def get_matching_subscribers_for_update(domains: list[str] | None) -> list[dict]:
    """Find verified users with topic_subscription=true whose sessions match the given domains."""
    if not domains:
        return []

    placeholders = ",".join("?" for _ in domains)
    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""
            SELECT DISTINCT u.id as user_id, u.email, u.unsubscribe_token,
                   cs.application_domain, cs.title as session_title
            FROM users u
            JOIN consultation_sessions cs ON cs.user_id = u.id
            WHERE u.email_verified = TRUE
              AND u.topic_subscription = TRUE
              AND cs.application_domain IN ({placeholders})
            """,
            domains,
        )
        rows = await cursor.fetchall()

    return [
        {
            "user_id": row["user_id"],
            "email": row["email"],
            "unsubscribe_token": row["unsubscribe_token"],
            "application_domain": row["application_domain"],
            "session_title": row["session_title"],
        }
        for row in rows
    ]


async def get_pending_followups_with_users() -> list[dict]:
    """Get pending follow-ups with user email info (via consultation_sessions.user_id)."""
    now = datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(_get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
                f.*,
                s.title as session_title,
                s.application_domain,
                u.email as user_email,
                u.email_verified,
                u.topic_subscription,
                u.unsubscribe_token
            FROM outcome_followup_schedule f
            JOIN consultation_sessions s ON f.session_id = s.id
            LEFT JOIN users u ON s.user_id = u.id
            WHERE f.scheduled_date <= ? AND f.status = 'pending'
            ORDER BY f.scheduled_date ASC
            """,
            (now,),
        )
        rows = await cursor.fetchall()

    return [
        {
            "id": row["id"],
            "session_id": row["session_id"],
            "session_title": row["session_title"],
            "application_domain": row["application_domain"],
            "followup_stage": row["followup_stage"],
            "scheduled_date": row["scheduled_date"],
            "status": row["status"],
            "user_email": row["user_email"] if row["email_verified"] and row["topic_subscription"] else None,
            "unsubscribe_token": row["unsubscribe_token"] if row["user_email"] else None,
            "created_at": row["created_at"],
        }
        for row in rows
    ]
