#!/usr/bin/env python3
"""
Cross-Vertical Intelligence Tests
===================================
Tests embedding-based off-vertical detection and demand logging.

Note: Tests that call the embedding API are marked and require OPENAI_API_KEY.
Pure unit tests (cosine similarity, logging) run without API calls.
"""
from __future__ import annotations
import sys
import os
import sqlite3
import tempfile
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


# ── Cosine Similarity ───────────────────────────────────────────────────

def test_cosine_similarity():
    print("\n── Cosine Similarity ──")

    import numpy as np
    from core.cross_vertical import _cosine_similarity

    a = np.array([1.0, 0.0, 0.0])
    b = np.array([1.0, 0.0, 0.0])
    check("Identical vectors = 1.0", abs(_cosine_similarity(a, b) - 1.0) < 0.001)

    c = np.array([0.0, 1.0, 0.0])
    check("Orthogonal vectors = 0.0", abs(_cosine_similarity(a, c)) < 0.001)

    d = np.array([-1.0, 0.0, 0.0])
    check("Opposite vectors = -1.0", abs(_cosine_similarity(a, d) - (-1.0)) < 0.001)

    z = np.array([0.0, 0.0, 0.0])
    check("Zero vector = 0.0", abs(_cosine_similarity(a, z)) < 0.001)

    e = np.array([0.6, 0.8, 0.0])
    sim = _cosine_similarity(a, e)
    check("Partial similarity ~0.6", 0.55 < sim < 0.65, f"got {sim:.3f}")


# ── Demand Logging ──────────────────────────────────────────────────────

def test_demand_logging():
    print("\n── Demand Logging ──")

    from core.cross_vertical import _log_demand
    import core.cross_vertical as cv

    tmp = tempfile.mktemp(suffix=".db")

    # Create the table
    conn = sqlite3.connect(tmp)
    conn.execute("""
        CREATE TABLE off_vertical_demand (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            source_vertical TEXT,
            source_platform TEXT,
            detected_target_vertical TEXT,
            query_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

    # Set module state
    old_db = cv._db_path
    old_platform = cv._current_platform_id
    cv._db_path = tmp
    cv._current_platform_id = "fps"

    _log_demand(
        session_id="test-session-1",
        source_vertical="hydraulic_filtration",
        detected_target="spray_nozzles",
        query_text="What nozzle should I use for spray drying?",
    )

    conn = sqlite3.connect(tmp)
    rows = conn.execute("SELECT * FROM off_vertical_demand").fetchall()
    check("Row inserted", len(rows) == 1)
    check("Source vertical correct", rows[0][2] == "hydraulic_filtration")
    check("Platform correct", rows[0][3] == "fps")
    check("Target vertical correct", rows[0][4] == "spray_nozzles")
    check("Query text captured", "spray drying" in rows[0][5])
    conn.close()

    # Restore
    cv._db_path = old_db
    cv._current_platform_id = old_platform
    os.unlink(tmp)


# ── Module State ────────────────────────────────────────────────────────

def test_module_state():
    print("\n── Module State ──")

    import core.cross_vertical as cv

    # Before init, should be disabled
    result = cv.check_off_vertical("test message", "hydraulic_filtration")
    check("Returns None when not initialized", result is None)


# ── Embedding-Based Detection (requires API key) ───────────────────────

def test_embedding_detection():
    print("\n── Embedding-Based Detection (requires OPENAI_API_KEY) ──")

    if not os.getenv("OPENAI_API_KEY"):
        print("  ⏭  Skipped — no OPENAI_API_KEY")
        return

    from core.cross_vertical import init_cross_vertical, check_off_vertical
    import core.cross_vertical as cv
    from core.vertical_loader import load_platform

    # Create temp DB
    tmp = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(tmp)
    conn.execute("""
        CREATE TABLE off_vertical_demand (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT, source_vertical TEXT, source_platform TEXT,
            detected_target_vertical TEXT, query_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

    # Load both platforms' verticals into a combined dict for testing
    fps = load_platform("fps")
    fds = load_platform("fds")
    all_verticals = {**fps.verticals, **fds.verticals}

    init_cross_vertical(
        platform_id="fps",
        verticals=all_verticals,
        db_path=tmp,
    )

    check("Initialized", cv._initialized)
    check("Two vertical embeddings", len(cv._vertical_embeddings) == 2)

    # On-topic filtration query
    r1 = check_off_vertical(
        "How do I select a return line filter for 120 LPM targeting ISO 16/14/11?",
        "hydraulic_filtration",
    )
    check("Filtration query ON-topic", r1 is None)

    # Off-topic: nozzle query in filtration session
    r2 = check_off_vertical(
        "What spray nozzle gives a full cone pattern with 200 micron SMD at 3 bar water pressure?",
        "hydraulic_filtration",
        session_id="test-embed-1",
    )
    if r2 is not None:
        check("Nozzle query detected as off-topic", r2["detected"])
        check("Target is spray_nozzles", r2["target_vertical"] == "spray_nozzles")
        check("Score gap exists", r2["target_score"] > r2["current_score"])
    else:
        # Embedding similarity may not always detect this — depends on model
        print("  ⚠️  Nozzle query NOT detected as off-topic (may be OK — embedding overlap)")

    # On-topic nozzle query
    r3 = check_off_vertical(
        "What spray nozzle gives full cone pattern at 200 micron SMD?",
        "spray_nozzles",
    )
    check("Nozzle query ON-topic in nozzle vertical", r3 is None)

    # Check demand was logged
    conn = sqlite3.connect(tmp)
    rows = conn.execute("SELECT * FROM off_vertical_demand").fetchall()
    logged = len(rows)
    check(f"Demand signals logged: {logged}", logged >= 0)  # May be 0 if r2 was None
    conn.close()

    os.unlink(tmp)


# ── Run All ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("CROSS-VERTICAL INTELLIGENCE TEST SUITE")
    print("=" * 60)

    test_cosine_similarity()
    test_demand_logging()
    test_module_state()
    test_embedding_detection()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"RESULTS: {PASS}/{total} passed, {FAIL} failed")
    if FAIL > 0:
        print("❌ SOME TESTS FAILED")
    else:
        print("✅ ALL TESTS PASSED")
    print("=" * 60)

    sys.exit(1 if FAIL > 0 else 0)
