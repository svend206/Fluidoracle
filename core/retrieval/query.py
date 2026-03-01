"""
Fluidoracle — Query Tool (v2: Hybrid Retrieval)
=======================================================
Simple interface for querying the knowledge base using the hybrid
retrieval pipeline (semantic + BM25 + parent-child + cross-encoder).

Usage:
    py -3.12 query.py "What nozzle produces the finest droplet size?"
    py -3.12 query.py "1/4GG-SS2.8 flow rate at 40 PSI" --top-k 3
    py -3.12 query.py "hollow cone vs full cone" --no-rerank
    py -3.12 query.py "TF28FC" --bm25-only
"""

import argparse
import sys

from .hybrid_search import search
from .config import VERBOSE


def display_results(query: str, results: list[dict], show_child: bool = False):
    """Pretty-print search results."""
    if not results:
        print(f"\nNo results found for: \"{query}\"")
        print("Try different search terms, or check that documents have been ingested.")
        return

    print(f"\n{'='*70}")
    print(f"  QUERY: {query}")
    print(f"  RESULTS: {len(results)}")
    print(f"{'='*70}")

    for i, r in enumerate(results, 1):
        score = r["rerank_score"]
        # Confidence label based on rerank score
        if score >= 0.75:
            conf = "HIGH"
        elif score >= 0.40:
            conf = "MEDIUM"
        else:
            conf = "LOW"

        print(f"\n╔══ Result {i}  [{conf} confidence: {score:.3f}] ══")
        print(f"║  Source: {r['source']}")
        print(f"║  Scores — Semantic: {r['semantic_score']:.3f} | BM25: {r['bm25_score']:.3f} | Combined: {r['combined_score']:.3f}")
        print(f"╠══ Context ══")

        # Word-wrap the parent text for readability
        text = r["parent_text"]
        line_width = 76
        lines = []
        for paragraph in text.split("\n"):
            while len(paragraph) > line_width:
                # Find a break point
                break_at = paragraph[:line_width].rfind(" ")
                if break_at == -1:
                    break_at = line_width
                lines.append(paragraph[:break_at])
                paragraph = paragraph[break_at:].lstrip()
            lines.append(paragraph)

        for line in lines:
            print(f"║  {line}")

        if show_child and r["child_text"] != r["parent_text"]:
            print(f"╠══ Matched fragment ══")
            print(f"║  {r['child_text'][:300]}")

        print(f"╚{'═'*68}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Query the hydraulic filter knowledge base (hybrid retrieval)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py -3.12 query.py "What causes uneven spray patterns?"
  py -3.12 query.py "1/4GG-SS2.8 flow rate" --bm25-only
  py -3.12 query.py "atomization mechanisms" --top-k 3
  py -3.12 query.py "FGD nozzle selection" --show-child
        """,
    )
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--no-rerank", action="store_true", help="Skip cross-encoder reranking (faster)")
    parser.add_argument("--semantic-only", action="store_true", help="Semantic search only")
    parser.add_argument("--bm25-only", action="store_true", help="BM25 keyword search only")
    parser.add_argument("--show-child", action="store_true", help="Also show the matched child chunk")

    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        return

    # Configure search mode
    kwargs = {
        "top_k": args.top_k,
        "use_reranker": not args.no_rerank,
    }
    if args.semantic_only:
        kwargs["semantic_weight"] = 1.0
        kwargs["bm25_weight"] = 0.0
    elif args.bm25_only:
        kwargs["semantic_weight"] = 0.0
        kwargs["bm25_weight"] = 1.0

    results = search(args.query, **kwargs)
    display_results(args.query, results, show_child=args.show_child)


if __name__ == "__main__":
    main()
