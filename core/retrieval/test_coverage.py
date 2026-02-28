"""
Hydraulic Filter Knowledge Base — Coverage Test Suite
==================================================
Runs curated test queries against the RAG pipeline to measure knowledge
base coverage by topic area. No Claude API calls — only retrieval (one
OpenAI embedding call per query, total cost < $0.01).

Usage:
    python test_coverage.py                              # Full suite
    python test_coverage.py --category evaporation       # One category
    python test_coverage.py --json                       # JSON output only
    python test_coverage.py --compare prev-report.json   # Diff vs baseline
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from .config import HIGH_CONFIDENCE_THRESHOLD, MEDIUM_CONFIDENCE_THRESHOLD
from . import config as _config_module
import verified_query as _vq_module
from .verified_query import verified_query


# ===========================================================================
# Test Query Suite — 52 queries across 13 categories
# ===========================================================================

TEST_QUERIES = [
    # ── Atomization Fundamentals (5) ──────────────────────────────────────
    {"category": "atomization_fundamentals",
     "query": "What are the primary breakup regimes for liquid jets and sheets?",
     "notes": "Rayleigh, wind-induced, prompt atomization regimes"},
    {"category": "atomization_fundamentals",
     "query": "How do Weber number and Ohnesorge number determine atomization quality?",
     "notes": "We/Oh regime maps — core dimensionless analysis"},
    {"category": "atomization_fundamentals",
     "query": "What is the Kelvin-Helmholtz instability mechanism in liquid sheet breakup?",
     "notes": "KH instability theory for flat fan nozzles"},
    {"category": "atomization_fundamentals",
     "query": "How does liquid viscosity affect the transition from dripping to jetting?",
     "notes": "Oh-number regime effects on breakup mode"},
    {"category": "atomization_fundamentals",
     "query": "What is the difference between primary and secondary atomization?",
     "notes": "Two-stage breakup process coverage"},

    # ── SMD Correlations (4) ──────────────────────────────────────────────
    {"category": "smd_correlations",
     "query": "What is the Lefebvre correlation for SMD in pressure-swirl atomizers?",
     "notes": "Most important SMD correlation"},
    {"category": "smd_correlations",
     "query": "How does the Nukiyama-Tanasawa equation predict droplet size in airblast nozzles?",
     "notes": "NT correlation for twin-fluid atomizers"},
    {"category": "smd_correlations",
     "query": "What is the Radcliffe correlation and what are its validity limits?",
     "notes": "Radcliffe 1955 correlation coverage"},
    {"category": "smd_correlations",
     "query": "How do I convert between SMD, Dv0.5, and Rosin-Rammler parameters?",
     "notes": "Droplet size distribution theory"},

    # ── Nozzle Types (6) ──────────────────────────────────────────────────
    {"category": "nozzle_types",
     "query": "How does a pressure-swirl hollow cone nozzle produce a conical spray pattern?",
     "notes": "Most common industrial nozzle type"},
    {"category": "nozzle_types",
     "query": "What is the difference between internal-mix and external-mix airblast atomizers?",
     "notes": "Twin-fluid nozzle design knowledge"},
    {"category": "nozzle_types",
     "query": "How do ultrasonic atomizing nozzles work and what droplet sizes do they produce?",
     "notes": "Specialized nozzle type coverage"},
    {"category": "nozzle_types",
     "query": "What are the advantages of rotary atomizers for spray drying applications?",
     "notes": "Rotary atomizer knowledge"},
    {"category": "nozzle_types",
     "query": "How does electrostatic atomization achieve monodisperse droplets?",
     "notes": "Electrostatic/cone-jet coverage"},
    {"category": "nozzle_types",
     "query": "What is the difference between flat fan and full cone spray patterns?",
     "notes": "Basic nozzle type comparison"},

    # ── Nozzle Selection and Sizing (5) ───────────────────────────────────
    {"category": "nozzle_selection",
     "query": "How do I calculate the flow number for a pressure-swirl nozzle?",
     "notes": "FN = mass_flow / sqrt(deltaP * rho)"},
    {"category": "nozzle_selection",
     "query": "What is the discharge coefficient Cd and how does it vary with nozzle geometry?",
     "notes": "Cd vs K-factor relationship"},
    {"category": "nozzle_selection",
     "query": "What turndown ratio can I expect from pressure atomizers versus airblast nozzles?",
     "notes": "Practical turndown knowledge (3:1 vs 20:1)"},
    {"category": "nozzle_selection",
     "query": "How do I select a nozzle for a specific spray angle and coverage width?",
     "notes": "Nozzle selection methodology"},
    {"category": "nozzle_selection",
     "query": "How does spray angle change with operating pressure and liquid viscosity?",
     "notes": "Angle-pressure-viscosity relationships"},

    # ── Droplet Size Measurement (4) ──────────────────────────────────────
    {"category": "droplet_measurement",
     "query": "What is Phase Doppler Anemometry and how does it measure droplet size?",
     "notes": "PDA/PDPA instrumentation knowledge"},
    {"category": "droplet_measurement",
     "query": "How does laser diffraction measure spray droplet size distributions?",
     "notes": "Malvern/Sympatec type measurement"},
    {"category": "droplet_measurement",
     "query": "What do Dv0.1, Dv0.5, and Dv0.9 represent in droplet size characterization?",
     "notes": "Volume-median diameter definitions"},
    {"category": "droplet_measurement",
     "query": "How is spray pattern uniformity measured using a patternator?",
     "notes": "CV% and patternation measurement"},

    # ── Evaporation and Heat Transfer (4) ─────────────────────────────────
    {"category": "evaporation_heat_transfer",
     "query": "What is the d-squared law for droplet evaporation?",
     "notes": "d^2 = d0^2 - K_evap*t fundamental relationship"},
    {"category": "evaporation_heat_transfer",
     "query": "How does the Ranz-Marshall correlation predict convective heat transfer to droplets?",
     "notes": "Nu = 2 + 0.6*Re^0.5*Pr^0.33"},
    {"category": "evaporation_heat_transfer",
     "query": "What determines the evaporation rate of a water spray in hot gas?",
     "notes": "K_evap values and temperature dependence"},
    {"category": "evaporation_heat_transfer",
     "query": "How does halving the SMD affect spray evaporation time?",
     "notes": "4x faster evaporation rule"},

    # ── Applications (6) ──────────────────────────────────────────────────
    {"category": "applications",
     "query": "How are hydraulic filters used in SCR urea injection systems for NOx reduction?",
     "notes": "SCR/automotive application knowledge"},
    {"category": "applications",
     "query": "What nozzle types are used in spray drying and what droplet sizes are typical?",
     "notes": "Spray drying application coverage"},
    {"category": "applications",
     "query": "How do fire suppression sprinkler nozzles work and what droplet sizes do they produce?",
     "notes": "Fire protection application"},
    {"category": "applications",
     "query": "What nozzle specifications are important for agricultural herbicide drift reduction?",
     "notes": "Agriculture/drift application"},
    {"category": "applications",
     "query": "How are hydraulic filters selected for gas cooling applications in FGD systems?",
     "notes": "Flue gas desulfurization"},
    {"category": "applications",
     "query": "What spray parameters matter for automotive paint coating quality?",
     "notes": "Coating/painting application"},

    # ── Nozzle Materials and Wear (3) ─────────────────────────────────────
    {"category": "materials_wear",
     "query": "When should I use tungsten carbide nozzles instead of stainless steel?",
     "notes": "Material selection for abrasive service"},
    {"category": "materials_wear",
     "query": "How does nozzle orifice wear affect flow rate and spray pattern over time?",
     "notes": "Wear progression knowledge"},
    {"category": "materials_wear",
     "query": "What is the expected service life of a stainless steel nozzle in abrasive slurry?",
     "notes": "Quantitative wear life data"},

    # ── Non-Newtonian Fluids (2) ──────────────────────────────────────────
    {"category": "non_newtonian",
     "query": "How does shear-thinning behavior affect atomization quality in hydraulic filters?",
     "notes": "Power-law fluid atomization coverage"},
    {"category": "non_newtonian",
     "query": "What nozzle types are recommended for atomizing high-viscosity non-Newtonian fluids?",
     "notes": "Practical non-Newtonian recommendations"},

    # ── Crossflow Injection (2) ───────────────────────────────────────────
    {"category": "crossflow_injection",
     "query": "What is the momentum flux ratio J and how does it affect spray penetration in crossflow?",
     "notes": "J = rho_l*v_l^2 / rho_g*v_g^2 crossflow correlation"},
    {"category": "crossflow_injection",
     "query": "How do I design a spray injection system for a gas duct crossflow?",
     "notes": "Practical crossflow injection design"},

    # ── CFD and Simulation (3) ────────────────────────────────────────────
    {"category": "cfd_simulation",
     "query": "What spray models are used in CFD simulation of nozzle atomization?",
     "notes": "TAB, WAVE, KH-RT breakup model knowledge"},
    {"category": "cfd_simulation",
     "query": "How is droplet size distribution specified as an initial condition in spray CFD?",
     "notes": "Rosin-Rammler input methodology"},
    {"category": "cfd_simulation",
     "query": "What are the limitations of RANS vs LES for simulating spray breakup?",
     "notes": "Turbulence modeling for sprays"},

    # ── Vendor Products (4) ───────────────────────────────────────────────
    {"category": "vendor_products",
     "query": "What are the specifications for Spraying Systems Co FullJet full cone nozzles?",
     "notes": "SSCo catalog data retrieval"},
    {"category": "vendor_products",
     "query": "What BETE nozzle models are recommended for fine mist generation?",
     "notes": "BETE product catalog coverage"},
    {"category": "vendor_products",
     "query": "What Lechler nozzle series are designed for gas cooling applications?",
     "notes": "Lechler catalog coverage"},
    {"category": "vendor_products",
     "query": "How do PNR Italia descaling nozzles compare to other manufacturers?",
     "notes": "PNR product data"},

    # ── Recent Research (4) ───────────────────────────────────────────────
    {"category": "recent_research",
     "query": "How does flash-boiling affect spray atomization quality?",
     "notes": "Flash-boiling spray dynamics knowledge"},
    {"category": "recent_research",
     "query": "What machine learning approaches have been applied to spray droplet size prediction?",
     "notes": "ML/AI for sprays coverage"},
    {"category": "recent_research",
     "query": "How is additive manufacturing being used to create novel nozzle geometries?",
     "notes": "3D-printed nozzle research"},
    {"category": "recent_research",
     "query": "What high-speed imaging techniques are used for modern spray diagnostics?",
     "notes": "Modern diagnostics research"},
]


# ===========================================================================
# Grading
# ===========================================================================

GRADE_THRESHOLDS = [
    (0.75, "A"),
    (0.55, "B"),
    (0.40, "C"),
    (0.25, "D"),
]

GRADE_COLORS = {"A": "\033[92m", "B": "\033[93m", "C": "\033[33m", "D": "\033[91m", "F": "\033[31m"}
CONF_COLORS = {"HIGH": "\033[92m", "MEDIUM": "\033[93m", "LOW": "\033[91m"}
RESET = "\033[0m"


def _grade(score: float) -> str:
    for threshold, g in GRADE_THRESHOLDS:
        if score >= threshold:
            return g
    return "F"


def _color(text: str, color_code: str, use_color: bool = True) -> str:
    return f"{color_code}{text}{RESET}" if use_color else text


# ===========================================================================
# Core Runner
# ===========================================================================

def run_coverage_test(
    categories: list[str] | None = None,
    suppress_gap_logging: bool = True,
) -> dict:
    """Run the full test suite and return a structured coverage report."""

    queries = TEST_QUERIES
    if categories:
        cats = set(categories)
        queries = [q for q in TEST_QUERIES if q["category"] in cats]
        if not queries:
            avail = sorted(set(q["category"] for q in TEST_QUERIES))
            print(f"No queries for category {categories}. Available: {avail}", file=sys.stderr)
            sys.exit(1)

    # Suppress gap logging and verbose output during test
    orig_log_gap = _vq_module.log_gap
    orig_verbose = _config_module.VERBOSE
    if suppress_gap_logging:
        _vq_module.log_gap = lambda query, confidence: None
    _config_module.VERBOSE = False

    results = []
    t_start = time.time()

    try:
        for i, q in enumerate(queries, 1):
            t0 = time.time()
            try:
                r = verified_query(q["query"], top_k=10, use_reranker=True)
                conf = r["confidence"]
                result = {
                    "category": q["category"],
                    "query": q["query"],
                    "notes": q["notes"],
                    "confidence_level": conf["level"],
                    "top_score": conf["top_score"],
                    "num_high_confidence": conf["num_high_confidence"],
                    "num_sources": conf["num_sources"],
                    "sources": conf["sources"],
                }
            except Exception as e:
                result = {
                    "category": q["category"],
                    "query": q["query"],
                    "notes": q["notes"],
                    "confidence_level": "LOW",
                    "top_score": 0.0,
                    "num_high_confidence": 0,
                    "num_sources": 0,
                    "sources": [],
                    "error": str(e),
                }

            results.append(result)
            elapsed = time.time() - t0
            level = result["confidence_level"]
            score = result["top_score"]
            print(
                f"  [{i:2d}/{len(queries)}] {q['category']:30s} "
                f"{level:6s} {score:.3f}  ({elapsed:.1f}s)  "
                f"{q['query'][:60]}",
                file=sys.stderr,
            )
    finally:
        _vq_module.log_gap = orig_log_gap
        _config_module.VERBOSE = orig_verbose

    runtime = time.time() - t_start

    # Build category summaries
    cat_data = defaultdict(list)
    for r in results:
        cat_data[r["category"]].append(r)

    cat_summaries = {}
    for cat, items in cat_data.items():
        scores = [it["top_score"] for it in items]
        avg = sum(scores) / len(scores) if scores else 0.0
        h = sum(1 for it in items if it["confidence_level"] == "HIGH")
        m = sum(1 for it in items if it["confidence_level"] == "MEDIUM")
        lo = sum(1 for it in items if it["confidence_level"] == "LOW")
        cat_summaries[cat] = {
            "avg_score": round(avg, 4),
            "high_count": h,
            "medium_count": m,
            "low_count": lo,
            "total": len(items),
            "grade": _grade(avg),
        }

    # Overall
    all_scores = [r["top_score"] for r in results]
    overall_avg = sum(all_scores) / len(all_scores) if all_scores else 0.0
    total_h = sum(1 for r in results if r["confidence_level"] == "HIGH")
    total_m = sum(1 for r in results if r["confidence_level"] == "MEDIUM")
    total_lo = sum(1 for r in results if r["confidence_level"] == "LOW")
    total = len(results)

    # Gaps (LOW-confidence queries)
    gaps = [
        {"category": r["category"], "query": r["query"], "top_score": r["top_score"], "notes": r["notes"]}
        for r in results if r["confidence_level"] == "LOW"
    ]

    # Weakest categories
    weakest = sorted(cat_summaries.items(), key=lambda x: x[1]["avg_score"])
    weakest_list = [{"category": c, "avg_score": s["avg_score"], "grade": s["grade"]} for c, s in weakest]

    return {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_queries": total,
            "categories_tested": sorted(cat_data.keys()),
            "runtime_seconds": round(runtime, 1),
        },
        "results": results,
        "category_summaries": cat_summaries,
        "overall": {
            "avg_score": round(overall_avg, 4),
            "high_count": total_h,
            "medium_count": total_m,
            "low_count": total_lo,
            "high_pct": round(total_h / total * 100, 1) if total else 0,
            "medium_pct": round(total_m / total * 100, 1) if total else 0,
            "low_pct": round(total_lo / total * 100, 1) if total else 0,
            "coverage_pct": round((total_h + total_m) / total * 100, 1) if total else 0,
            "grade": _grade(overall_avg),
        },
        "gaps": gaps,
        "weakest_categories": weakest_list,
    }


# ===========================================================================
# Report Printing
# ===========================================================================

def print_report(report: dict, use_color: bool = True) -> None:
    meta = report["metadata"]
    overall = report["overall"]
    cats = report["category_summaries"]
    gaps = report["gaps"]
    weakest = report["weakest_categories"]

    def cg(grade):
        return _color(grade, GRADE_COLORS.get(grade, ""), use_color)

    print()
    print("=" * 70)
    print(f"  KNOWLEDGE BASE COVERAGE REPORT")
    print(f"  {meta['timestamp'][:10]} | {meta['total_queries']} queries | "
          f"{len(meta['categories_tested'])} categories | {meta['runtime_seconds']}s")
    print("=" * 70)

    # Category table
    print()
    print(f"  {'Category':<32s} {'Avg':>5s}  {'H':>2s} {'M':>2s} {'L':>2s}  Grade")
    print(f"  {'─' * 60}")

    # Sort by avg score descending
    sorted_cats = sorted(cats.items(), key=lambda x: -x[1]["avg_score"])
    for cat, s in sorted_cats:
        grade_str = cg(s["grade"])
        print(f"  {cat:<32s} {s['avg_score']:5.3f}  {s['high_count']:2d} {s['medium_count']:2d} {s['low_count']:2d}  {grade_str}")

    # Overall
    print(f"  {'─' * 60}")
    og = cg(overall["grade"])
    print(f"  OVERALL: avg={overall['avg_score']:.3f} | "
          f"HIGH: {overall['high_pct']:.0f}% | "
          f"MEDIUM: {overall['medium_pct']:.0f}% | "
          f"LOW: {overall['low_pct']:.0f}% | "
          f"Coverage: {overall['coverage_pct']:.0f}% | "
          f"Grade: {og}")

    # Weakest categories
    print()
    print("  WEAKEST TOPICS (prioritize for content acquisition):")
    for i, w in enumerate(weakest[:5], 1):
        wg = cg(w["grade"])
        print(f"    {i}. {w['category']:<30s} {w['avg_score']:.3f}  {wg}")

    # Gaps
    if gaps:
        print()
        print(f"  GAPS — {len(gaps)} LOW-confidence queries:")
        by_cat = defaultdict(list)
        for g in gaps:
            by_cat[g["category"]].append(g)
        for cat in sorted(by_cat.keys()):
            for g in by_cat[cat]:
                q_short = g["query"][:65]
                print(f"    [{cat}] \"{q_short}\" ({g['top_score']:.3f})")
    else:
        print()
        print("  No gaps found — all queries scored MEDIUM or above!")

    print()
    print("=" * 70)


# ===========================================================================
# Baseline Comparison
# ===========================================================================

def compare_reports(current: dict, baseline_path: str) -> None:
    with open(baseline_path, "r") as f:
        baseline = json.load(f)

    print()
    print("=" * 70)
    print("  COVERAGE COMPARISON")
    print(f"  Baseline: {baseline['metadata']['timestamp'][:10]}")
    print(f"  Current:  {current['metadata']['timestamp'][:10]}")
    print("=" * 70)

    # Overall
    b_cov = baseline["overall"]["coverage_pct"]
    c_cov = current["overall"]["coverage_pct"]
    delta = c_cov - b_cov
    sign = "+" if delta >= 0 else ""
    print(f"\n  Overall coverage: {b_cov:.0f}% -> {c_cov:.0f}% ({sign}{delta:.0f}pp)")
    print(f"  Overall grade:   {baseline['overall']['grade']} -> {current['overall']['grade']}")

    # Category changes
    b_cats = baseline.get("category_summaries", {})
    c_cats = current.get("category_summaries", {})
    all_cats = sorted(set(list(b_cats.keys()) + list(c_cats.keys())))

    improved = []
    degraded = []
    for cat in all_cats:
        b_score = b_cats.get(cat, {}).get("avg_score", 0)
        c_score = c_cats.get(cat, {}).get("avg_score", 0)
        diff = c_score - b_score
        if diff > 0.05:
            improved.append((cat, b_score, c_score, diff))
        elif diff < -0.05:
            degraded.append((cat, b_score, c_score, diff))

    if improved:
        print(f"\n  IMPROVED ({len(improved)}):")
        for cat, b, c, d in sorted(improved, key=lambda x: -x[3]):
            print(f"    {cat:<32s} {b:.3f} -> {c:.3f}  (+{d:.3f})")

    if degraded:
        print(f"\n  DEGRADED ({len(degraded)}):")
        for cat, b, c, d in sorted(degraded, key=lambda x: x[3]):
            print(f"    {cat:<32s} {b:.3f} -> {c:.3f}  ({d:.3f})")

    # Gap changes
    b_gaps = set(g["query"] for g in baseline.get("gaps", []))
    c_gaps = set(g["query"] for g in current.get("gaps", []))
    resolved = b_gaps - c_gaps
    new_gaps = c_gaps - b_gaps

    if resolved:
        print(f"\n  RESOLVED GAPS ({len(resolved)}):")
        for q in sorted(resolved):
            print(f"    + {q[:70]}")

    if new_gaps:
        print(f"\n  NEW GAPS ({len(new_gaps)}):")
        for q in sorted(new_gaps):
            print(f"    - {q[:70]}")

    print()
    print("=" * 70)


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Knowledge Base Coverage Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  python test_coverage.py                          # Full suite\n"
               "  python test_coverage.py --category nozzle_types  # One category\n"
               "  python test_coverage.py --json                   # JSON only\n"
               "  python test_coverage.py --compare baseline.json  # Diff\n",
    )
    parser.add_argument("--category", type=str, help="Run only queries in this category")
    parser.add_argument("--json", action="store_true", help="Output JSON only (no terminal report)")
    parser.add_argument("--compare", type=str, metavar="BASELINE", help="Compare to baseline report JSON")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path (default: coverage-report.json)")
    parser.add_argument("--list-categories", action="store_true", help="List available categories and exit")
    args = parser.parse_args()

    if args.list_categories:
        cats = sorted(set(q["category"] for q in TEST_QUERIES))
        for c in cats:
            count = sum(1 for q in TEST_QUERIES if q["category"] == c)
            print(f"  {c} ({count} queries)")
        return

    cats = [args.category] if args.category else None
    print(f"\n  Running coverage test ({len(TEST_QUERIES) if not cats else sum(1 for q in TEST_QUERIES if q['category'] in cats)} queries)...\n",
          file=sys.stderr)

    report = run_coverage_test(categories=cats)

    # Save JSON
    output_path = args.output or str(Path(__file__).parent / "coverage-report.json")
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved to {output_path}", file=sys.stderr)

    # Output
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report, use_color=not args.no_color)

    if args.compare:
        compare_reports(report, args.compare)


if __name__ == "__main__":
    main()
