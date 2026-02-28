from __future__ import annotations
"""
Hydraulic Filter Expert — Verified Query System (v2: Hybrid Retrieval)
=================================================================
Wraps the hybrid retrieval engine with the 5-step verification protocol:

  1. Multi-chunk retrieval (hybrid search returns diverse results)
  2. Source citation on every claim
  3. Contradiction detection across sources
  4. Confidence scoring (from cross-encoder reranker)
  5. Physics sanity flag (prompts the user/agent to check)

Also includes:
  - Gap tracker: logs queries with poor retrieval for knowledge acquisition
  - Correction pipeline: records and ingests error corrections
  - Session debrief: summarizes what went well and what didn't

Usage:
    py -3.12 verified_query.py "What nozzle produces the finest droplet size?"
    py -3.12 verified_query.py --gaps
    py -3.12 verified_query.py --correct
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import re as _re

from .hybrid_search import search
from .config import (
    GAP_TRACKER_PATH,
    CORRECTIONS_DIR,
    HIGH_CONFIDENCE_THRESHOLD,
    MEDIUM_CONFIDENCE_THRESHOLD,
    VERBOSE,
)


# ===========================================================================
# Vendor Detection (loaded from oracle.db — platform-level manufacturer registry)
# ===========================================================================

# Cached vendor patterns loaded from the database on first use.
# Format: list of (compiled_regex, manufacturer_name) tuples.
_vendor_patterns_cache: list[tuple[_re.Pattern, str]] | None = None


def _load_vendor_patterns() -> list[tuple[_re.Pattern, str]]:
    """Load manufacturer filename patterns from oracle.db.
    
    Falls back to an empty list if the database or table doesn't exist.
    Patterns are stored as JSON arrays in manufacturers.filename_patterns.
    """
    patterns = []
    try:
        # Import from oracle-pipeline's db module
        # The DB path is resolved relative to the oracle-pipeline location
        import sqlite3
        # Look for oracle.db in known locations
        candidates = [
            Path.home() / "Projects" / "oracle" / "oracle-pipeline" / "oracle.db",
            Path(__file__).parent.parent.parent.parent / "oracle" / "oracle-pipeline" / "oracle.db",
        ]
        db_path = None
        for candidate in candidates:
            if candidate.exists():
                db_path = candidate
                break
        
        if db_path is None:
            if VERBOSE:
                print("  [!] oracle.db not found — vendor detection disabled")
            return []
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, filename_patterns FROM manufacturers WHERE filename_patterns IS NOT NULL"
        ).fetchall()
        conn.close()
        
        for row in rows:
            name = row["name"]
            raw_patterns = json.loads(row["filename_patterns"])
            for pat in raw_patterns:
                try:
                    patterns.append((_re.compile(pat), name))
                except _re.error:
                    if VERBOSE:
                        print(f"  [!] Invalid regex pattern for {name}: {pat}")
        
        if VERBOSE and patterns:
            print(f"  Loaded {len(patterns)} vendor filename patterns from oracle.db")
    
    except Exception as e:
        if VERBOSE:
            print(f"  [!] Could not load vendor patterns from oracle.db: {e}")
    
    return patterns


def _detect_vendor(source_filename: str) -> str | None:
    """Return the manufacturer name for a source filename, or None if academic/neutral.
    
    Patterns are loaded from oracle.db (manufacturers.filename_patterns) on first call
    and cached for the session.
    """
    global _vendor_patterns_cache
    if _vendor_patterns_cache is None:
        _vendor_patterns_cache = _load_vendor_patterns()
    
    for pattern, vendor in _vendor_patterns_cache:
        if pattern.search(source_filename):
            return vendor
    return None


# Display name overrides are now minimal — most humanization comes from
# the source filename structure and manufacturer name from the database.
_DISPLAY_NAME_OVERRIDES: dict[str, str] = {}


def _humanize_source(source_filename: str) -> str:
    """Convert an internal source filename to a human-readable display name.

    Examples:
        "ILASS2015_34_Vesely.pdf"        → "ILASS 2015 — Vesely (Paper 34)"
        "cat75a_hydraulic_filters.pdf"        → "Spraying Systems — Industrial Spray Products (Cat. 75A)"
        "BETE_1218USA_Catalog.pdf"        → "BETE — 1218USA Catalog"
        "Lefebvre_Atomization_Ch3.pdf"    → "Lefebvre Atomization Ch3"
    """
    # Strip extension
    name = source_filename
    for ext in (".pdf", ".docx", ".md", ".txt"):
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break

    # Check overrides first
    name_lower = name.lower()
    for key, display in _DISPLAY_NAME_OVERRIDES.items():
        if name_lower.startswith(key.lower()):
            return display

    # ILASS conference papers: "ILASS2015_34_Vesely" → "ILASS 2015 — Vesely (Paper 34)"
    m = _re.match(r"^ILASS(\d{4})[_-](\d+)[_-](.+)$", name)
    if m:
        year, number, author = m.group(1), m.group(2), m.group(3)
        author = author.replace("_", " ").replace("-", " ").strip()
        return f"ILASS {year} — {author} (Paper {number})"

    # Generic ILASS: "ILASS2020_keynote" → "ILASS 2020 — Keynote"
    m = _re.match(r"^ILASS(\d{4})[_-](.+)$", name)
    if m:
        year, rest = m.group(1), m.group(2)
        rest = rest.replace("_", " ").replace("-", " ").strip().title()
        return f"ILASS {year} — {rest}"

    # Vendor documents: prepend vendor name with em-dash separator
    vendor = _detect_vendor(source_filename)
    if vendor:
        # Strip vendor prefix from the display name to avoid redundancy
        display = name
        for prefix in (vendor.lower(), vendor.replace("/", "").lower(),
                       vendor.split("/")[0].lower()):
            if display.lower().startswith(prefix):
                display = display[len(prefix):].lstrip("_- ")
                break
        # Also strip common code prefixes that the vendor pattern matched
        display = _re.sub(r"^(cat7\d?[a-z]?|c\d{2}[a-z]|b\d{2,3}[a-z]|cs\d|tm\d|wp\d|psb|EKB\d)[_-]?", "", display)
        display = display.replace("_", " ").replace("-", " ").strip()
        if display:
            display = display[0].upper() + display[1:] if display else ""
            return f"{vendor} — {display}"
        return vendor

    # Fallback: clean up underscores/hyphens and title-case
    display = name.replace("_", " ").replace("-", " ").strip()
    return display if display else source_filename


# ===========================================================================
# Confidence Assessment
# ===========================================================================

def assess_confidence(results: list[dict]) -> dict:
    """Analyze retrieval results and produce a structured confidence assessment.
    
    Returns:
        {
            "level": "HIGH" | "MEDIUM" | "LOW",
            "top_score": float,
            "num_results": int,
            "num_high_confidence": int,
            "num_sources": int,
            "sources": [list of unique source filenames],
            "contradictions": [list of potential contradictions],
            "reasoning": str,
        }
    """
    if not results:
        return {
            "level": "LOW",
            "top_score": 0.0,
            "num_results": 0,
            "num_high_confidence": 0,
            "num_sources": 0,
            "sources": [],
            "contradictions": [],
            "reasoning": "No relevant documents found in the knowledge base.",
        }

    scores = [r["rerank_score"] for r in results]
    top_score = max(scores)
    high_conf_count = sum(1 for s in scores if s >= HIGH_CONFIDENCE_THRESHOLD)
    sources = list(set(r["source"] for r in results))

    # Determine confidence level
    if top_score >= HIGH_CONFIDENCE_THRESHOLD and high_conf_count >= 2 and len(sources) >= 2:
        level = "HIGH"
        reasoning = (
            f"Multiple high-confidence matches ({high_conf_count}) from "
            f"{len(sources)} independent sources. Top rerank score: {top_score:.3f}."
        )
    elif top_score >= MEDIUM_CONFIDENCE_THRESHOLD:
        level = "MEDIUM"
        reasons = []
        if high_conf_count < 2:
            reasons.append(f"only {high_conf_count} high-confidence match(es)")
        if len(sources) < 2:
            reasons.append("single source only")
        reasoning = (
            f"Moderate confidence. Top score: {top_score:.3f}. "
            f"Limitations: {'; '.join(reasons)}. Verify before relying on this."
        )
    else:
        level = "LOW"
        reasoning = (
            f"Low confidence. Best match scored {top_score:.3f}. "
            f"The knowledge base may not cover this topic well. "
            f"Consider adding relevant source material."
        )

    # Simple contradiction detection: check if different sources have very different
    # content for the same query (indicated by both being high-ranked but from different sources)
    contradictions = []
    if len(results) >= 2 and len(sources) >= 2:
        # If top two results are from different sources and both scored well,
        # flag for manual review (a more sophisticated system would compare content)
        r1, r2 = results[0], results[1]
        if (r1["source"] != r2["source"]
            and r1["rerank_score"] >= MEDIUM_CONFIDENCE_THRESHOLD
            and r2["rerank_score"] >= MEDIUM_CONFIDENCE_THRESHOLD):
            # Check for different content overlap — crude but useful
            words1 = set(r1["parent_text"].lower().split())
            words2 = set(r2["parent_text"].lower().split())
            overlap = len(words1 & words2) / max(len(words1 | words2), 1)
            if overlap < 0.15:
                contradictions.append({
                    "source_1": r1["source"],
                    "source_2": r2["source"],
                    "overlap": round(overlap, 3),
                    "note": "Low content overlap between top results from different sources. Review both.",
                })

    # Vendor diversity analysis
    vendors = set()
    for r in results:
        v = _detect_vendor(r["source"])
        if v is not None:
            vendors.add(v)
    dominant_vendor = None
    if len(vendors) == 1:
        dominant_vendor = next(iter(vendors))

    return {
        "level": level,
        "top_score": round(top_score, 4),
        "num_results": len(results),
        "num_high_confidence": high_conf_count,
        "num_sources": len(sources),
        "sources": sources,
        "contradictions": contradictions,
        "reasoning": reasoning,
        "dominant_vendor": dominant_vendor,
    }


# ===========================================================================
# Gap Tracker
# ===========================================================================

def log_gap(query: str, confidence: dict):
    """Log a query that had low confidence — signals a knowledge gap."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "confidence_level": confidence["level"],
        "top_score": confidence["top_score"],
        "num_results": confidence["num_results"],
        "sources_checked": confidence["sources"],
    }

    with open(GAP_TRACKER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    if VERBOSE:
        print(f"\n  ⚠ Gap logged: \"{query}\" (confidence: {confidence['level']})")


def show_gaps():
    """Display all logged knowledge gaps, sorted by frequency and recency."""
    if not GAP_TRACKER_PATH.exists():
        print("\nNo gaps logged yet. The gap tracker activates when queries return low-confidence results.")
        return

    gaps = []
    with open(GAP_TRACKER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                gaps.append(json.loads(line))

    if not gaps:
        print("\nNo gaps logged yet.")
        return

    print(f"\n{'='*70}")
    print(f"  KNOWLEDGE GAPS ({len(gaps)} logged)")
    print(f"  These are topics where the knowledge base couldn't provide confident answers.")
    print(f"  Use this list to prioritize what documents to acquire and ingest next.")
    print(f"{'='*70}\n")

    # Count frequency of similar queries (rough grouping by first few words)
    from collections import Counter
    query_counts = Counter(g["query"].lower() for g in gaps)

    # Show most recent first, with frequency
    seen = set()
    for gap in reversed(gaps):
        q = gap["query"]
        q_lower = q.lower()
        if q_lower in seen:
            continue
        seen.add(q_lower)

        freq = query_counts[q_lower]
        freq_label = f" (asked {freq}x)" if freq > 1 else ""
        print(f"  [{gap['confidence_level']}] {q}{freq_label}")
        print(f"       Score: {gap['top_score']} | Results: {gap['num_results']} | {gap['timestamp'][:10]}")
        print()


# ===========================================================================
# Correction Pipeline
# ===========================================================================

def record_correction():
    """Interactive correction recording. Captures wrong answer and correct answer."""
    print("\n" + "=" * 60)
    print("CORRECTION PIPELINE")
    print("Record what the agent got wrong and what the correct answer is.")
    print("=" * 60 + "\n")

    query = input("Original question: ").strip()
    if not query:
        print("Cancelled.")
        return

    wrong_answer = input("What the agent said (wrong): ").strip()
    correct_answer = input("What the correct answer is: ").strip()
    source = input("Source of correct answer (optional): ").strip()
    notes = input("Additional notes (optional): ").strip()

    correction = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "wrong_answer": wrong_answer,
        "correct_answer": correct_answer,
        "source": source,
        "notes": notes,
        "status": "pending_ingestion",
    }

    # Save to corrections directory
    filename = f"correction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = CORRECTIONS_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(correction, f, indent=2)

    print(f"\n✓ Correction saved: {filepath}")
    print(f"\nTo ingest this correction into the knowledge base:")
    print(f"  py -3.12 ingest.py \"{filepath}\" --collection corrections --tags \"correction,high-priority\"")


# ===========================================================================
# Verified Query (Main)
# ===========================================================================

def verified_query(
    query: str,
    top_k: int = 10,
    use_reranker: bool = True,
    semantic_weight: float | None = None,
    bm25_weight: float | None = None,
    child_collection: str | None = None,
    parent_collection: str | None = None,
    bm25_index_path: str | None = None,
) -> dict:
    """Execute a verified query against the knowledge base.
    
    Args:
        query: Natural language question
        top_k: Number of results to return
        use_reranker: Whether to use cross-encoder reranking
        semantic_weight: Override semantic search weight (0-1). Default uses config value (0.60).
        bm25_weight: Override BM25 keyword weight (0-1). Default uses config value (0.40).
    
    Returns:
        {
            "query": str,
            "results": list[dict],       # retrieval results with parent text
            "confidence": dict,           # confidence assessment
            "citations": list[str],       # formatted citation strings
            "warnings": list[str],        # any warnings or flags
            "gap_logged": bool,           # whether a gap was logged
        }
    """
    # Run hybrid search
    results = search(
        query,
        top_k=top_k,
        use_reranker=use_reranker,
        semantic_weight=semantic_weight,
        bm25_weight=bm25_weight,
        child_collection=child_collection,
        parent_collection=parent_collection,
        bm25_index_path=bm25_index_path,
    )

    # Assess confidence
    confidence = assess_confidence(results)

    # Build citations (scores kept in results dict for logging; stripped from user-facing text)
    citations = []
    for i, r in enumerate(results, 1):
        citations.append(
            f"[{i}] {_humanize_source(r['source'])}"
        )

    # Build warnings
    warnings = []
    if confidence["level"] == "LOW":
        warnings.append("LOW CONFIDENCE: Knowledge base may not cover this topic adequately.")
    if confidence["contradictions"]:
        for c in confidence["contradictions"]:
            warnings.append(
                f"POTENTIAL CONTRADICTION: {c['source_1']} and {c['source_2']} "
                f"show low content overlap ({c['overlap']:.1%}). Review both sources."
            )
    if confidence["num_sources"] == 1 and confidence["num_results"] > 0:
        warnings.append("SINGLE SOURCE: All results come from one document. Cross-reference if possible.")
    if confidence.get("dominant_vendor") and confidence["num_results"] > 1:
        warnings.append(
            f"SINGLE VENDOR: Retrieved product information is primarily from "
            f"{confidence['dominant_vendor']}. Consider cross-referencing with "
            f"other manufacturers."
        )

    # Log gap if confidence is low
    gap_logged = False
    if confidence["level"] == "LOW":
        log_gap(query, confidence)
        gap_logged = True

    return {
        "query": query,
        "results": results,
        "confidence": confidence,
        "citations": citations,
        "warnings": warnings,
        "gap_logged": gap_logged,
    }


# ===========================================================================
# Display
# ===========================================================================

def display_verified_result(result: dict):
    """Pretty-print a verified query result."""
    q = result["query"]
    conf = result["confidence"]

    print(f"\n{'='*70}")
    print(f"  VERIFIED QUERY: {q}")
    print(f"{'='*70}")

    # Confidence summary
    level = conf["level"]
    emoji = {"HIGH": "✓", "MEDIUM": "~", "LOW": "✗"}[level]
    print(f"\n  {emoji} Confidence: {level}")
    print(f"    {conf['reasoning']}")

    # Warnings
    if result["warnings"]:
        print(f"\n  ⚠ Warnings:")
        for w in result["warnings"]:
            print(f"    • {w}")

    # Sources
    if result["citations"]:
        print(f"\n  Sources:")
        for c in result["citations"][:5]:
            print(f"    {c}")

    # Top results
    if result["results"]:
        print(f"\n  Retrieved Context ({len(result['results'])} chunks):")
        for i, r in enumerate(result["results"][:5], 1):
            print(f"\n  ── Chunk {i} [{r['source']}] (score: {r['rerank_score']:.3f}) ──")
            # Truncate for display
            text = r["parent_text"]
            if len(text) > 500:
                text = text[:500] + "..."
            for line in text.split("\n"):
                print(f"  │ {line}")
    else:
        print(f"\n  No relevant context found.")

    if result["gap_logged"]:
        print(f"\n  📝 This query was logged as a knowledge gap.")

    print(f"\n{'='*70}\n")


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hydraulic Filter Expert — Verified Query System v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py -3.12 verified_query.py "What causes uneven spray patterns?"
  py -3.12 verified_query.py "1/4GG-SS2.8 specifications" --top-k 3
  py -3.12 verified_query.py --gaps
  py -3.12 verified_query.py --correct
        """,
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--top-k", type=int, default=10, help="Number of chunks to retrieve (default: 10)")
    parser.add_argument("--no-rerank", action="store_true", help="Skip cross-encoder reranking")
    parser.add_argument("--gaps", action="store_true", help="Show logged knowledge gaps")
    parser.add_argument("--correct", action="store_true", help="Record a correction")

    args = parser.parse_args()

    if args.gaps:
        show_gaps()
    elif args.correct:
        record_correction()
    elif args.query:
        result = verified_query(args.query, top_k=args.top_k, use_reranker=not args.no_rerank)
        display_verified_result(result)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
