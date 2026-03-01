#!/usr/bin/env python3
"""
Fluidoracle Test Harness
=========================
Runs structured test cases against the Fluidoracle /api/ask endpoint.
Scoring is pure keyword/concept matching — zero LLM API tokens.

Usage:
    python3 tests/run_tests.py                          # test live site
    python3 tests/run_tests.py --url http://localhost:8000  # test local
    python3 tests/run_tests.py --case mining-01         # single test
    python3 tests/run_tests.py --case-study wind_turbine # all wind tests
    python3 tests/run_tests.py --verbose                # show full responses
    python3 tests/run_tests.py --output results.json    # save results to file
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import textwrap
from datetime import datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_URL = "https://fluidoracle.com"
FIXTURES_PATH = Path(__file__).parent / "fixtures.json"
REQUEST_TIMEOUT = 120  # seconds — RAG pipeline can be slow on complex queries
DELAY_BETWEEN_REQUESTS = 1.0  # seconds — be polite to the API


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_response(response_text: str, test_case: dict) -> dict:
    """
    Score a response against a test case. Returns a scoring dict.
    Pure string matching — no LLM calls.
    """
    text_lower = response_text.lower()
    results = {}

    # 1. Required keywords — all must be present
    required_kw = test_case.get("required_keywords", [])
    kw_hits = [kw for kw in required_kw if kw.lower() in text_lower]
    kw_misses = [kw for kw in required_kw if kw.lower() not in text_lower]
    results["keyword_hits"] = kw_hits
    results["keyword_misses"] = kw_misses
    results["keywords_pass"] = len(kw_misses) == 0

    # 2. Required concepts — each concept is a list of synonyms, at least one must match
    required_concepts = test_case.get("required_concepts", [])
    min_concepts = test_case.get("min_concepts", len(required_concepts))
    concept_results = []
    for concept_group in required_concepts:
        matched = next((term for term in concept_group if term.lower() in text_lower), None)
        concept_results.append({
            "concept": concept_group[0],
            "synonyms_checked": concept_group,
            "matched": matched,
            "pass": matched is not None
        })
    concepts_passed = sum(1 for c in concept_results if c["pass"])
    results["concept_detail"] = concept_results
    results["concepts_passed"] = concepts_passed
    results["concepts_required"] = min_concepts
    results["concepts_pass"] = concepts_passed >= min_concepts

    # 3. Must-not-contain — any match is a fail
    must_not = test_case.get("must_not_contain", [])
    violations = [phrase for phrase in must_not if phrase.lower() in text_lower]
    results["must_not_violations"] = violations
    results["must_not_pass"] = len(violations) == 0

    # 4. Confidence floor
    # (confidence is passed in separately from the API response)
    results["confidence_floor"] = test_case.get("confidence_floor", "LOW")

    # Overall pass: all three checks must pass
    results["pass"] = (
        results["keywords_pass"]
        and results["concepts_pass"]
        and results["must_not_pass"]
    )

    return results


def check_confidence(api_confidence: str, floor: str) -> bool:
    """Return True if api_confidence meets or exceeds floor."""
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    return order.get(api_confidence.upper(), 0) >= order.get(floor.upper(), 0)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_test(base_url: str, test_case: dict, verbose: bool = False) -> dict:
    """Run a single test case. Returns a result dict."""
    url = f"{base_url.rstrip('/')}/api/ask"
    payload = {"question": test_case["question"]}

    start = time.time()
    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        elapsed = time.time() - start
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return {
            "id": test_case["id"],
            "title": test_case["title"],
            "status": "ERROR",
            "error": "Request timed out",
            "elapsed_s": REQUEST_TIMEOUT,
        }
    except Exception as e:
        return {
            "id": test_case["id"],
            "title": test_case["title"],
            "status": "ERROR",
            "error": str(e),
            "elapsed_s": time.time() - start,
        }

    answer = data.get("answer", "")
    api_confidence = data.get("confidence", "LOW")
    sources = data.get("sources", [])

    scoring = score_response(answer, test_case)
    confidence_ok = check_confidence(api_confidence, test_case.get("confidence_floor", "LOW"))
    overall_pass = scoring["pass"] and confidence_ok

    result = {
        "id": test_case["id"],
        "case_study": test_case.get("case_study", ""),
        "title": test_case["title"],
        "status": "PASS" if overall_pass else "FAIL",
        "elapsed_s": round(elapsed, 1),
        "api_confidence": api_confidence,
        "confidence_floor": test_case.get("confidence_floor", "LOW"),
        "confidence_ok": confidence_ok,
        "scoring": scoring,
        "sources_count": len(sources),
        "sources": sources,
        "question": test_case["question"],
        "answer": answer,
    }

    if verbose:
        result["answer_preview"] = answer[:500]

    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

PASS_ICON = "✅"
FAIL_ICON = "❌"
WARN_ICON = "⚠️ "
ERROR_ICON = "🔴"

def print_result(result: dict, verbose: bool = False):
    icon = PASS_ICON if result["status"] == "PASS" else (ERROR_ICON if result["status"] == "ERROR" else FAIL_ICON)
    conf_ok = "✓" if result.get("confidence_ok", False) else "✗"

    print(f"\n{icon} [{result['id']}] {result['title']}")
    print(f"   Confidence: {result.get('api_confidence','?')} (floor: {result.get('confidence_floor','?')}) {conf_ok}  |  Sources: {result.get('sources_count',0)}  |  {result.get('elapsed_s','?')}s")

    if result["status"] == "ERROR":
        print(f"   {ERROR_ICON} ERROR: {result.get('error','')}")
        return

    scoring = result.get("scoring", {})

    # Keywords
    if scoring.get("keyword_misses"):
        print(f"   {WARN_ICON} Missing keywords: {', '.join(scoring['keyword_misses'])}")

    # Concepts
    concepts = scoring.get("concept_detail", [])
    passed = scoring.get("concepts_passed", 0)
    required = scoring.get("concepts_required", 0)
    icon_c = "✓" if scoring.get("concepts_pass") else "✗"
    print(f"   Concepts: {passed}/{required} required {icon_c}")
    for c in concepts:
        mark = "  ✓" if c["pass"] else "  ✗"
        matched = f"→ '{c['matched']}'" if c["pass"] else f"(checked: {', '.join(c['synonyms_checked'])})"
        print(f"     {mark} {c['concept']} {matched}")

    # Must-not violations
    if scoring.get("must_not_violations"):
        print(f"   {FAIL_ICON} MUST-NOT violations: {', '.join(scoring['must_not_violations'])}")

    # Verbose: show answer preview
    if verbose and result.get("answer"):
        print(f"\n   Answer preview:")
        wrapped = textwrap.fill(result["answer"][:600], width=90, initial_indent="   ", subsequent_indent="   ")
        print(wrapped)
        if len(result["answer"]) > 600:
            print("   [... truncated ...]")


def print_summary(results: list[dict]):
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    errors = sum(1 for r in results if r["status"] == "ERROR")

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  Total:  {total}")
    print(f"  {PASS_ICON} Pass:   {passed}  ({100*passed//total if total else 0}%)")
    print(f"  {FAIL_ICON} Fail:   {failed}")
    print(f"  {ERROR_ICON} Error:  {errors}")

    # By case study
    by_case: dict[str, list] = {}
    for r in results:
        cs = r.get("case_study", "other")
        by_case.setdefault(cs, []).append(r)

    print("\n  By case study:")
    for cs, rs in sorted(by_case.items()):
        p = sum(1 for r in rs if r["status"] == "PASS")
        print(f"    {cs}: {p}/{len(rs)} passed")

    # Flag failures
    failures = [r for r in results if r["status"] != "PASS"]
    if failures:
        print(f"\n  Failed tests:")
        for r in failures:
            print(f"    {FAIL_ICON if r['status']=='FAIL' else ERROR_ICON} {r['id']}: {r['title']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fluidoracle test harness")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL of Fluidoracle API")
    parser.add_argument("--case", help="Run a single test case by ID")
    parser.add_argument("--case-study", help="Run all tests for a case study (e.g. mining)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show answer previews")
    parser.add_argument("--output", "-o", help="Save results to JSON file")
    parser.add_argument("--fixtures", default=str(FIXTURES_PATH), help="Path to fixtures.json")
    args = parser.parse_args()

    # Load fixtures
    fixtures_path = Path(args.fixtures)
    if not fixtures_path.exists():
        print(f"ERROR: Fixtures file not found: {fixtures_path}", file=sys.stderr)
        sys.exit(1)

    with open(fixtures_path) as f:
        fixtures = json.load(f)

    test_cases = fixtures["test_cases"]

    # Filter by --case or --case-study
    if args.case:
        test_cases = [tc for tc in test_cases if tc["id"] == args.case]
        if not test_cases:
            print(f"ERROR: No test case with id '{args.case}'", file=sys.stderr)
            sys.exit(1)
    elif args.case_study:
        test_cases = [tc for tc in test_cases if tc.get("case_study") == args.case_study]
        if not test_cases:
            print(f"ERROR: No test cases for case_study '{args.case_study}'", file=sys.stderr)
            sys.exit(1)

    print(f"Fluidoracle Test Harness")
    print(f"Target: {args.url}")
    print(f"Tests:  {len(test_cases)}")
    print(f"Time:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    results = []
    for i, tc in enumerate(test_cases):
        print(f"\n[{i+1}/{len(test_cases)}] Running: {tc['id']} — {tc['title']}")
        result = run_test(args.url, tc, verbose=args.verbose)
        print_result(result, verbose=args.verbose)
        results.append(result)

        # Rate limiting — don't hammer the API
        if i < len(test_cases) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    print_summary(results)

    # Save output
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump({
                "run_at": datetime.now().isoformat(),
                "target_url": args.url,
                "total": len(results),
                "passed": sum(1 for r in results if r["status"] == "PASS"),
                "results": results,
            }, f, indent=2)
        print(f"\nResults saved to: {output_path}")

    # Exit code: 0 if all passed, 1 if any failures
    all_passed = all(r["status"] == "PASS" for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
