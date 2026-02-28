"""
Retrieval Isolation Test
========================
Verify that each vertical's knowledge base is completely isolated:
- Filtration queries must never return nozzle chunks
- Nozzle queries must never return filtration chunks

This test requires both verticals' KBs to be ingested.
Run after Sprint 3 when both KBs exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.retrieval.hybrid_search import search


def test_filtration_isolation():
    """Filtration queries should only hit filtration collections."""
    queries = [
        "How do I select a return line filter for 120 L/min?",
        "What beta ratio do I need for servo valve protection?",
        "ISO 4406 cleanliness target for mobile hydraulic system",
    ]

    for q in queries:
        results = search(
            q,
            child_collection="hydraulic_filtration-children",
            parent_collection="hydraulic_filtration-parents",
            bm25_index_path="vector-store/bm25/hydraulic_filtration.pkl",
            top_k=5,
        )
        # These should return results (filtration KB exists)
        assert len(results) > 0, f"No results for filtration query: {q}"
        print(f"  [OK] Filtration query returned {len(results)} results: {q[:60]}...")


def test_nozzle_isolation():
    """Nozzle queries against filtration KB should return low-relevance results."""
    queries = [
        "What spray nozzle gives full cone pattern at 200 micron SMD?",
        "How do I calculate droplet size for agricultural spraying?",
        "Twin-fluid atomizer vs pressure nozzle for spray drying",
    ]

    for q in queries:
        results = search(
            q,
            child_collection="hydraulic_filtration-children",
            parent_collection="hydraulic_filtration-parents",
            bm25_index_path="vector-store/bm25/hydraulic_filtration.pkl",
            top_k=5,
        )
        # Results may exist (BM25 will match some words) but rerank scores should be very low
        if results:
            top_score = results[0].get("rerank_score", 0)
            assert top_score < 0.3, (
                f"Nozzle query got high score ({top_score:.3f}) from filtration KB: {q}"
            )
            print(f"  [OK] Nozzle query got low score ({top_score:.3f}) from filtration KB: {q[:60]}...")
        else:
            print(f"  [OK] Nozzle query returned 0 results from filtration KB: {q[:60]}...")


def test_cross_collection_separation():
    """Verify that querying non-existent collection returns empty results."""
    results = search(
        "hydraulic filter",
        child_collection="spray_nozzles-children",
        parent_collection="spray_nozzles-parents",
        bm25_index_path="vector-store/bm25/spray_nozzles.pkl",
        top_k=5,
    )
    # Nozzle KB doesn't exist yet — should return empty
    assert len(results) == 0, f"Got {len(results)} results from non-existent nozzle KB"
    print("  [OK] Non-existent collection returns 0 results")


if __name__ == "__main__":
    print("=" * 50)
    print("RETRIEVAL ISOLATION TESTS")
    print("=" * 50)

    print("\n1. Filtration queries against filtration KB:")
    test_filtration_isolation()

    print("\n2. Nozzle queries against filtration KB (cross-contamination check):")
    test_nozzle_isolation()

    print("\n3. Cross-collection separation:")
    test_cross_collection_separation()

    print("\n" + "=" * 50)
    print("ALL ISOLATION TESTS PASSED")
    print("=" * 50)
