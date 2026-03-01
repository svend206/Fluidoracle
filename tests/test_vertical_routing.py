#!/usr/bin/env python3
"""
Vertical Routing Tests
=======================
Validates that per-request vertical config resolution works correctly
and that the consultation engine accepts and uses vertical_config params.

Zero LLM calls — tests routing plumbing, not AI responses.
"""
from __future__ import annotations
import sys
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


# ── Vertical Config Resolution ──────────────────────────────────────────

def test_resolve_vertical_config():
    print("\n── Vertical Config Resolution ──")

    # Simulate what the route handler does
    from core.vertical_loader import load_platform

    # FPS session
    fps = load_platform("fps")
    hf = fps.verticals.get("hydraulic_filtration")
    check("FPS/HF resolved", hf is not None)
    check("HF has correct child collection", hf.child_collection == "hydraulic_filtration-children")
    check("HF has correct parent collection", hf.parent_collection == "hydraulic_filtration-parents")
    check("HF gathering prompt populated", len(hf.gathering_prompt) > 100)
    check("HF answering prompt populated", len(hf.answering_prompt) > 100)

    # FDS session
    fds = load_platform("fds")
    sn = fds.verticals.get("spray_nozzles")
    check("FDS/SN resolved", sn is not None)
    check("SN has correct child collection", sn.child_collection == "spray_nozzles-children")
    check("SN gathering prompt populated", len(sn.gathering_prompt) > 100)
    check("SN answering prompt different from HF", sn.answering_prompt != hf.answering_prompt)
    check("SN gathering prompt different from HF", sn.gathering_prompt != hf.gathering_prompt)

    # Missing vertical returns None gracefully
    result = fps.verticals.get("nonexistent_vertical")
    check("Missing vertical returns None", result is None)


# ── Engine Entry Points Accept vertical_config ──────────────────────────

def test_engine_signatures():
    print("\n── Engine Signatures ──")

    import inspect
    from core.consultation_engine import (
        generate_consultation_response,
        generate_consultation_response_stream,
        _retrieval_kwargs,
    )

    sig1 = inspect.signature(generate_consultation_response)
    check("generate_consultation_response has vertical_config",
          "vertical_config" in sig1.parameters)
    check("vertical_config defaults to None",
          sig1.parameters["vertical_config"].default is None)

    sig2 = inspect.signature(generate_consultation_response_stream)
    check("generate_consultation_response_stream has vertical_config",
          "vertical_config" in sig2.parameters)


# ── Retrieval Kwargs Builder ────────────────────────────────────────────

def test_retrieval_kwargs():
    print("\n── Retrieval Kwargs Builder ──")

    from core.consultation_engine import _retrieval_kwargs
    from core.vertical_loader import load_platform

    fps = load_platform("fps")
    hf = fps.verticals["hydraulic_filtration"]
    kwargs = _retrieval_kwargs(hf)

    check("Has child_collection", kwargs.get("child_collection") == "hydraulic_filtration-children")
    check("Has parent_collection", kwargs.get("parent_collection") == "hydraulic_filtration-parents")
    check("Has bm25_index_path", "hydraulic_filtration.pkl" in str(kwargs.get("bm25_index_path", "")))

    fds = load_platform("fds")
    sn = fds.verticals["spray_nozzles"]
    kwargs2 = _retrieval_kwargs(sn)

    check("SN child_collection", kwargs2.get("child_collection") == "spray_nozzles-children")
    check("Collections differ", kwargs["child_collection"] != kwargs2["child_collection"])


# ── Verified Query Accepts Collection Overrides ─────────────────────────

def test_verified_query_signature():
    print("\n── Verified Query Signature ──")

    import inspect
    from core.retrieval.verified_query import verified_query

    sig = inspect.signature(verified_query)
    check("Has child_collection param", "child_collection" in sig.parameters)
    check("Has parent_collection param", "parent_collection" in sig.parameters)
    check("Has bm25_index_path param", "bm25_index_path" in sig.parameters)


# ── Route Helper Simulation ─────────────────────────────────────────────

def test_route_resolution():
    print("\n── Route-Level Resolution ──")

    from core.vertical_loader import load_platform

    def resolve_vertical_config(session: dict):
        """Mirrors _resolve_vertical_config from routes/consultation.py"""
        vid = session.get("vertical_id")
        pid = session.get("platform_id", "fps")
        if not vid:
            return None
        try:
            platform = load_platform(pid)
            return platform.verticals.get(vid)
        except Exception:
            return None

    # Happy path — FPS filtration
    vc = resolve_vertical_config({"vertical_id": "hydraulic_filtration", "platform_id": "fps"})
    check("FPS/HF resolves from session", vc is not None)
    check("Correct vertical_id", vc.vertical_id == "hydraulic_filtration")

    # Happy path — FDS nozzles
    vc2 = resolve_vertical_config({"vertical_id": "spray_nozzles", "platform_id": "fds"})
    check("FDS/SN resolves from session", vc2 is not None)
    check("Correct vertical_id", vc2.vertical_id == "spray_nozzles")

    # Cross-platform mismatch (nozzle vertical doesn't exist in FPS)
    vc3 = resolve_vertical_config({"vertical_id": "spray_nozzles", "platform_id": "fps"})
    check("Cross-platform returns None", vc3 is None)

    # Missing vertical_id
    vc4 = resolve_vertical_config({"platform_id": "fps"})
    check("Missing vertical_id returns None", vc4 is None)

    # Bad platform_id
    vc5 = resolve_vertical_config({"vertical_id": "hydraulic_filtration", "platform_id": "nonexistent"})
    check("Bad platform_id returns None", vc5 is None)

    # Empty session
    vc6 = resolve_vertical_config({})
    check("Empty session returns None", vc6 is None)


# ── Prompt Isolation ────────────────────────────────────────────────────

def test_prompt_isolation():
    print("\n── Prompt Isolation ──")

    from core.vertical_loader import load_platform

    fps = load_platform("fps")
    hf = fps.verticals["hydraulic_filtration"]
    fds = load_platform("fds")
    sn = fds.verticals["spray_nozzles"]

    # Verify domain-specific content in prompts
    check("HF gathering mentions filtration",
          "filter" in hf.gathering_prompt.lower() or "hydraulic" in hf.gathering_prompt.lower())
    check("SN gathering mentions spray/nozzle",
          "spray" in sn.gathering_prompt.lower() or "nozzle" in sn.gathering_prompt.lower())

    # Verify answering prompts are different
    check("Answering prompts differ", hf.answering_prompt != sn.answering_prompt)

    # Verify HF answering has ISO/beta content
    check("HF answering has ISO reference",
          "iso" in hf.answering_prompt.lower() or "4406" in hf.answering_prompt)

    # Verify SN answering has atomization/SMD content
    check("SN answering has spray content",
          "atomiz" in sn.answering_prompt.lower() or "smd" in sn.answering_prompt.lower()
          or "droplet" in sn.answering_prompt.lower())


# ── Run All ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("VERTICAL ROUTING TEST SUITE")
    print("Zero LLM calls — routing plumbing tests")
    print("=" * 60)

    test_resolve_vertical_config()
    test_engine_signatures()
    test_retrieval_kwargs()
    test_verified_query_signature()
    test_route_resolution()
    test_prompt_isolation()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"RESULTS: {PASS}/{total} passed, {FAIL} failed")
    if FAIL > 0:
        print("❌ SOME TESTS FAILED")
    else:
        print("✅ ALL TESTS PASSED")
    print("=" * 60)

    sys.exit(1 if FAIL > 0 else 0)
