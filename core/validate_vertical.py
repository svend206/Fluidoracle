#!/usr/bin/env python3
"""
Fluidoracle — Vertical Onboarding Validator
=============================================
Validates that each registered vertical meets all required configuration
and knowledge base quality standards before going live.

Usage:
    python3 -m core.validate_vertical              # validate all platforms
    python3 -m core.validate_vertical --platform fps
    python3 -m core.validate_vertical --platform fps --vertical hydraulic_filtration
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS_COUNT = 0
FAIL_COUNT = 0


def ok(msg: str):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"    ✅ {msg}")


def fail(msg: str):
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"    ❌ {msg}")


def check(label: str, condition: bool, detail: str = ""):
    if condition:
        ok(label)
    else:
        fail(f"{label}" + (f" — {detail}" if detail else ""))


def validate_vertical(platform_id: str, vertical_id: str, vc) -> bool:
    """Validate a single vertical. Returns True if all checks pass."""
    global PASS_COUNT, FAIL_COUNT
    start_fail = FAIL_COUNT

    print(f"\n  [{platform_id}/{vertical_id}]")

    src_dir = Path(f"platforms/{platform_id}/verticals/{vertical_id}")

    # ── Config files ──────────────────────────────────────────────────────
    check("config.py exists", (src_dir / "config.py").exists())
    check("gathering_prompt.md exists", (src_dir / "gathering_prompt.md").exists())
    check("answering_prompt.md exists", (src_dir / "answering_prompt.md").exists())
    check("identity.md exists", (src_dir / "identity.md").exists())
    check("domains.py exists", (src_dir / "domains.py").exists())
    check("reference_data.py exists", (src_dir / "reference_data.py").exists())

    # ── Prompt content ────────────────────────────────────────────────────
    check("gathering_prompt non-empty", len(vc.gathering_prompt) > 100,
          f"only {len(vc.gathering_prompt)} chars")
    check("answering_prompt non-empty", len(vc.answering_prompt) > 100,
          f"only {len(vc.answering_prompt)} chars")

    # ── Domains ───────────────────────────────────────────────────────────
    check("≥3 application domains", len(vc.application_domains) >= 3,
          f"found {len(vc.application_domains)}")

    # ── Example questions ─────────────────────────────────────────────────
    check("≥3 example questions", len(vc.example_questions) >= 3,
          f"found {len(vc.example_questions)}")

    # ── ChromaDB collections ──────────────────────────────────────────────
    try:
        import chromadb
        client = chromadb.PersistentClient(path="vector-store")
        children = client.get_collection(vc.child_collection)
        parents = client.get_collection(vc.parent_collection)
        child_count = children.count()
        parent_count = parents.count()
        check(f"children collection exists ({child_count} chunks)", True)
        check(f"≥100 child chunks", child_count >= 100, f"found {child_count}")
        check(f"≥50 parent chunks", parent_count >= 50, f"found {parent_count}")
    except Exception as e:
        fail(f"ChromaDB collections: {e}")
        fail("≥100 child chunks (skipped)")
        fail("≥50 parent chunks (skipped)")

    # ── BM25 index ────────────────────────────────────────────────────────
    bm25_path = Path(vc.bm25_index_path) if vc.bm25_index_path else None
    check("BM25 index exists", bm25_path is not None and bm25_path.exists(),
          f"{bm25_path}")

    # ── Test fixtures ─────────────────────────────────────────────────────
    fixture_path = Path(f"tests/fixtures/{vertical_id}.json")
    check("test fixtures exist", fixture_path.exists())
    if fixture_path.exists():
        import json
        with open(fixture_path) as f:
            fixtures = json.load(f)
        test_cases = fixtures.get("test_cases", [])
        check("≥5 test cases in fixtures", len(test_cases) >= 5,
              f"found {len(test_cases)}")

    # ── Retrieval quality ─────────────────────────────────────────────────
    print("    [retrieval quality check]")
    try:
        from core.retrieval.hybrid_search import search

        test_queries = []
        query_thresholds = {}
        if fixture_path.exists():
            # Prefer non-pending test cases (those with min_rerank_score > 0 or no note)
            eligible = [tc for tc in test_cases if not tc.get("note")]
            if not eligible:
                eligible = test_cases
            for tc in eligible[:3]:
                q = tc["question"]
                test_queries.append(q)
                query_thresholds[q] = tc.get("min_rerank_score", 0.5)
        if not test_queries:
            test_queries = vc.example_questions[:3]

        scores = []
        for q in test_queries[:3]:
            results = search(
                q, top_k=3, use_reranker=True,
                child_collection=vc.child_collection,
                parent_collection=vc.parent_collection,
                bm25_index_path=vc.bm25_index_path,
            )
            threshold = query_thresholds.get(q, 0.5)
            if results:
                top_score = results[0].get("rerank_score", results[0].get("reranker_score", results[0].get("score", 0)))
                scores.append(top_score)
                check(f"  '{q[:50]}...' → {top_score:.3f}", top_score > threshold,
                      f"score {top_score:.3f} < {threshold}")
            else:
                fail(f"  '{q[:50]}...' → no results")

        if scores:
            avg = sum(scores) / len(scores)
            avg_threshold = sum(query_thresholds.get(q, 0.5) for q in test_queries[:len(scores)]) / len(scores)
            check(f"  Average reranker score {avg:.3f} > {avg_threshold:.2f}", avg > avg_threshold)

    except Exception as e:
        fail(f"Retrieval quality check failed: {e}")

    return FAIL_COUNT == start_fail


def validate_isolation(platform_a: str, vid_a: str, vc_a, platform_b: str, vid_b: str, vc_b):
    """Cross-vertical retrieval isolation check."""
    print(f"\n  [isolation: {vid_a} ↔ {vid_b}]")
    try:
        from core.retrieval.hybrid_search import search

        # Filtration query against nozzle KB
        q1 = vc_a.example_questions[0]
        results = search(
            q1, top_k=3, use_reranker=True,
            child_collection=vc_b.child_collection,
            parent_collection=vc_b.parent_collection,
            bm25_index_path=vc_b.bm25_index_path,
        )
        score = results[0].get("reranker_score", 0) if results else 0
        check(f"  {vid_a} query → {vid_b} KB: score {score:.3f} < 0.5 (isolated)", score < 0.5,
              f"score {score:.3f} is suspiciously high — possible KB contamination")

        # Nozzle query against filtration KB
        q2 = vc_b.example_questions[0]
        results2 = search(
            q2, top_k=3, use_reranker=True,
            child_collection=vc_a.child_collection,
            parent_collection=vc_a.parent_collection,
            bm25_index_path=vc_a.bm25_index_path,
        )
        score2 = results2[0].get("reranker_score", 0) if results2 else 0
        check(f"  {vid_b} query → {vid_a} KB: score {score2:.3f} < 0.5 (isolated)", score2 < 0.5,
              f"score {score2:.3f} is suspiciously high — possible KB contamination")

    except Exception as e:
        fail(f"Isolation check failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Fluidoracle vertical onboarding validator")
    parser.add_argument("--platform", help="Platform ID to validate (default: all)")
    parser.add_argument("--vertical", help="Vertical ID to validate (default: all in platform)")
    args = parser.parse_args()

    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    print("=" * 60)
    print("FLUIDORACLE VERTICAL ONBOARDING VALIDATOR")
    print("=" * 60)

    from core.vertical_loader import load_platform

    platform_ids = [args.platform] if args.platform else ["fps", "fds"]
    all_verticals = {}  # platform_id → {vertical_id: vc}

    for pid in platform_ids:
        try:
            platform = load_platform(pid)
            print(f"\n{'='*40}")
            print(f"Platform: {platform.display_name} ({pid})")
            print(f"{'='*40}")
        except Exception as e:
            print(f"\n❌ Failed to load platform '{pid}': {e}")
            continue

        verticals_to_check = {}
        if args.vertical:
            if args.vertical in platform.verticals:
                verticals_to_check = {args.vertical: platform.verticals[args.vertical]}
            else:
                print(f"  ❌ Vertical '{args.vertical}' not found in {pid}")
        else:
            verticals_to_check = platform.verticals

        all_verticals[pid] = verticals_to_check

        for vid, vc in verticals_to_check.items():
            validate_vertical(pid, vid, vc)

    # Cross-vertical isolation (only when both platforms validated)
    if "fps" in all_verticals and "fds" in all_verticals:
        fps_verts = all_verticals["fps"]
        fds_verts = all_verticals["fds"]
        if fps_verts and fds_verts:
            fps_vid, fps_vc = next(iter(fps_verts.items()))
            fds_vid, fds_vc = next(iter(fds_verts.items()))
            print(f"\n{'='*40}")
            print("Cross-vertical Isolation")
            print(f"{'='*40}")
            validate_isolation("fps", fps_vid, fps_vc, "fds", fds_vid, fds_vc)

    print(f"\n{'='*60}")
    total = PASS_COUNT + FAIL_COUNT
    print(f"RESULTS: {PASS_COUNT}/{total} checks passed, {FAIL_COUNT} failed")
    if FAIL_COUNT > 0:
        print("❌ VALIDATION FAILED — address failures before going live")
    else:
        print("✅ ALL CHECKS PASSED — vertical(s) ready for production")
    print("=" * 60)

    sys.exit(1 if FAIL_COUNT > 0 else 0)


if __name__ == "__main__":
    main()
