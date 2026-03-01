from __future__ import annotations

"""
Fluidoracle — Hybrid Retrieval Engine
==============================================
Three-stage retrieval pipeline optimized for engineering content:

  Stage 1: HYBRID SEARCH (Semantic + BM25)
    - Semantic search via ChromaDB embeddings → finds conceptually relevant chunks
    - BM25 keyword search → finds exact term matches (model numbers, codes, values)
    - Results merged with weighted scoring (default 60/40 semantic/BM25)

  Stage 2: PARENT-CHILD RESOLUTION
    - Search matches child chunks (small, precise)
    - Returns parent chunks (large, contextual) for LLM consumption
    - Deduplicates when multiple children map to the same parent

  Stage 3: CROSS-ENCODER RERANKING
    - Reranks merged candidates using a cross-encoder model
    - Reads query + chunk together (not independently) for accurate relevance
    - Runs locally — no API cost

Usage:
    from hybrid_search import search
    results = search("What nozzle produces the finest droplet size?", top_k=5)

Each result is a dict:
    {
        "parent_id": str,
        "parent_text": str,           # the context chunk for the LLM
        "child_text": str,            # the matched child chunk
        "source": str,                # source filename
        "rerank_score": float,        # cross-encoder confidence (0-1)
        "semantic_score": float,      # cosine similarity score
        "bm25_score": float,          # BM25 relevance score
        "metadata": dict,             # full metadata
    }
"""

import re
import sys
import numpy as np
from pathlib import Path

import chromadb
from openai import OpenAI

from .config import (
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    VECTOR_STORE_PATH,
    CHILD_COLLECTION,
    PARENT_COLLECTION,
    SEMANTIC_WEIGHT,
    BM25_WEIGHT,
    SEMANTIC_TOP_K,
    BM25_TOP_K,
    RERANK_CANDIDATES,
    FINAL_TOP_K,
    CROSS_ENCODER_MODEL,
    VERBOSE,
)
from .ingest import load_bm25_index, tokenize_for_bm25

# ---------------------------------------------------------------------------
# Clients (initialized lazily)
# ---------------------------------------------------------------------------
_openai_client = None
_chroma_client = None
_cross_encoder = None
_bm25_data = {}  # keyed by index path


def _get_openai():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _get_chroma():
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_PATH))
    return _chroma_client


def _get_bm25_index(bm25_index_path: str | None = None):
    """Load BM25 index into memory once per path; reuse on subsequent calls (~263MB each)."""
    global _bm25_data
    cache_key = str(bm25_index_path or "default")
    if cache_key not in _bm25_data:
        if VERBOSE:
            print("  Loading BM25 index into memory (first call)...")
        _bm25_data[cache_key] = load_bm25_index(index_path=bm25_index_path)
    return _bm25_data[cache_key]


def _get_cross_encoder():
    """Load cross-encoder model. Downloads ~80MB on first use, then cached."""
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        if VERBOSE:
            print(f"  Loading cross-encoder: {CROSS_ENCODER_MODEL}")
        _cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)
    return _cross_encoder


# ===========================================================================
# Stage 1: Hybrid Search (Semantic + BM25)
# ===========================================================================

def _semantic_search(
    query: str,
    top_k: int = SEMANTIC_TOP_K,
    where_filter: dict | None = None,
    child_collection: str | None = None,
) -> list[dict]:
    """Search child chunks using cosine similarity on embeddings.
    
    Args:
        where_filter: Optional ChromaDB where clause for metadata filtering.
            Example: {"source": "REFERENCE-ISO-Cleanliness-Codes.md"}
        child_collection: Override the default child collection name.
    """
    client = _get_chroma()
    collection_name = child_collection or CHILD_COLLECTION

    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        if VERBOSE:
            print("  [!] Child collection not found. Have you ingested documents?")
        return []

    if collection.count() == 0:
        return []

    # Embed the query
    response = _get_openai().embeddings.create(
        model=EMBEDDING_MODEL,
        input=[query],
    )
    query_embedding = response.data[0].embedding

    # Search (with optional metadata filter)
    query_kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": min(top_k, collection.count()),
        "include": ["documents", "metadatas", "distances"],
    }
    if where_filter:
        query_kwargs["where"] = where_filter
    
    results = collection.query(**query_kwargs)

    hits = []
    for i in range(len(results["ids"][0])):
        # ChromaDB returns cosine distance; convert to similarity
        distance = results["distances"][0][i]
        similarity = 1.0 - distance  # cosine similarity = 1 - cosine distance

        hits.append({
            "child_id": results["ids"][0][i],
            "child_text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "semantic_score": max(0.0, similarity),
            "bm25_score": 0.0,
            "source": "semantic",
        })

    return hits


def _bm25_search(
    query: str,
    top_k: int = BM25_TOP_K,
    metadata_filter: dict | None = None,
    bm25_index_path: str | None = None,
) -> list[dict]:
    """Search child chunks using BM25 keyword matching.
    
    Args:
        metadata_filter: Optional dict for post-hoc metadata filtering.
            Only simple equality filters are supported (e.g., {"source": "file.md"}).
            Complex ChromaDB operators ($contains, $gt, etc.) are NOT supported here.
        bm25_index_path: Override the default BM25 index file path.
    """
    bm25_data = _get_bm25_index(bm25_index_path=bm25_index_path)
    if bm25_data is None:
        if VERBOSE:
            print("  [!] BM25 index not found. Run: py -3.12 ingest.py --rebuild-bm25")
        return []

    bm25 = bm25_data["bm25"]
    ids = bm25_data["ids"]
    documents = bm25_data["documents"]
    metadatas = bm25_data["metadatas"]

    # Tokenize query
    query_tokens = tokenize_for_bm25(query)
    if not query_tokens:
        return []

    # Score all documents
    scores = bm25.get_scores(query_tokens)

    # Get top-k indices
    top_indices = np.argsort(scores)[::-1][:top_k]

    hits = []
    for idx in top_indices:
        score = float(scores[idx])
        if score <= 0:
            continue  # skip zero-score results

        # Post-hoc metadata filtering for BM25 results
        if metadata_filter:
            meta = metadatas[idx]
            skip = False
            for key, value in metadata_filter.items():
                if isinstance(value, str):
                    if meta.get(key) != value:
                        skip = True
                        break
                # Skip complex operators (ChromaDB $contains etc.) — not supported here
            if skip:
                continue

        hits.append({
            "child_id": ids[idx],
            "child_text": documents[idx],
            "metadata": metadatas[idx],
            "semantic_score": 0.0,
            "bm25_score": score,
            "source": "bm25",
        })

    return hits


# ---------------------------------------------------------------------------
# Query-adaptive BM25 weighting
# ---------------------------------------------------------------------------

# Patterns that indicate a specification/standards query where exact keyword
# matching is more valuable than semantic similarity.
_SPEC_QUERY_PATTERNS = re.compile(
    r"(ISO\s*\d{3,5}|NAS\s*\d{3,4}|SAE\s*AS?\s*\d{3,4}|ASTM\s*D\s*\d{3,4}"
    r"|β[_\s]*\d|beta\s*ratio|µm\s*\(c\)|micron"
    r"|part\s*#|model\s*#|P/N\s*\d|cat(alog)?\s*#"
    r"|\b[A-Z]{2,4}[-\s]?\d{4,})",  # manufacturer part numbers like DHP-1234
    re.IGNORECASE,
)

# Boosted BM25 weight when spec patterns are detected (vs default 0.40)
SPEC_BM25_WEIGHT = 0.75
SPEC_SEMANTIC_WEIGHT = 0.25


def _adaptive_weights(query: str) -> tuple[float, float]:
    """Return (semantic_weight, bm25_weight) based on query content.
    
    Boosts BM25 weight for queries containing ISO codes, part numbers,
    standard references, or specific technical identifiers where exact
    keyword matching outperforms semantic similarity.
    """
    if _SPEC_QUERY_PATTERNS.search(query):
        return SPEC_SEMANTIC_WEIGHT, SPEC_BM25_WEIGHT
    return SEMANTIC_WEIGHT, BM25_WEIGHT


def _merge_results(
    semantic_hits: list[dict],
    bm25_hits: list[dict],
    max_candidates: int = RERANK_CANDIDATES,
    semantic_weight: float = SEMANTIC_WEIGHT,
    bm25_weight: float = BM25_WEIGHT,
) -> list[dict]:
    """Merge semantic and BM25 results using Reciprocal Rank Fusion (RRF).
    
    RRF is more robust than linear score combination because it's based on
    rank positions rather than raw scores, making it insensitive to different
    score distributions between methods.
    
    RRF formula: score = 1/(k + rank_semantic) + 1/(k + rank_bm25)
    where k=60 is the standard smoothing constant.
    
    The semantic_weight and bm25_weight parameters scale each method's
    RRF contribution, allowing query-adaptive weighting.
    """
    RRF_K = 60  # standard smoothing constant

    # Build rank maps (1-indexed: rank 1 = best)
    semantic_ranks = {}
    for rank, hit in enumerate(semantic_hits, 1):
        semantic_ranks[hit["child_id"]] = rank

    bm25_ranks = {}
    for rank, hit in enumerate(bm25_hits, 1):
        bm25_ranks[hit["child_id"]] = rank

    # Merge all unique child IDs
    all_ids = set(semantic_ranks.keys()) | set(bm25_ranks.keys())
    
    # Build a lookup for hit data
    hit_data = {}
    for hit in semantic_hits + bm25_hits:
        cid = hit["child_id"]
        if cid not in hit_data:
            hit_data[cid] = hit.copy()
            hit_data[cid]["semantic_score"] = 0.0
            hit_data[cid]["bm25_score"] = 0.0
        # Preserve the actual scores from whichever method found this chunk
        if hit.get("semantic_score", 0) > 0:
            hit_data[cid]["semantic_score"] = hit["semantic_score"]
        if hit.get("bm25_score", 0) > 0:
            hit_data[cid]["bm25_score"] = hit["bm25_score"]

    # Compute RRF scores
    merged = []
    for cid in all_ids:
        entry = hit_data[cid]
        
        sem_rrf = semantic_weight / (RRF_K + semantic_ranks.get(cid, len(semantic_hits) + 1))
        bm25_rrf = bm25_weight / (RRF_K + bm25_ranks.get(cid, len(bm25_hits) + 1))
        
        entry["combined_score"] = sem_rrf + bm25_rrf
        
        if cid in semantic_ranks and cid in bm25_ranks:
            entry["source"] = "both"
        elif cid in semantic_ranks:
            entry["source"] = "semantic"
        else:
            entry["source"] = "bm25"
        
        merged.append(entry)

    # Sort by RRF score and take top candidates
    merged.sort(key=lambda x: x["combined_score"], reverse=True)
    return merged[:max_candidates]


# ===========================================================================
# Stage 2: Parent-Child Resolution
# ===========================================================================

def _resolve_parents(candidates: list[dict], parent_collection: str | None = None) -> list[dict]:
    """For each matched child chunk, fetch the corresponding parent chunk.
    
    Deduplicates: if multiple children point to the same parent,
    keep the child with the highest score and return the parent once.
    """
    client = _get_chroma()
    collection_name = parent_collection or PARENT_COLLECTION

    try:
        parent_col = client.get_collection(name=collection_name)
    except Exception:
        # No parent collection — fall back to using child text as context
        if VERBOSE:
            print("  [!] Parent collection not found. Using child chunks as context.")
        for c in candidates:
            c["parent_id"] = c["child_id"]
            c["parent_text"] = c["child_text"]
        return candidates

    # Collect unique parent IDs and track best child per parent
    best_per_parent = {}
    for candidate in candidates:
        pid = candidate["metadata"].get("parent_id", candidate["child_id"])
        score = candidate.get("combined_score", 0.0)

        if pid not in best_per_parent or score > best_per_parent[pid].get("combined_score", 0.0):
            best_per_parent[pid] = {**candidate, "parent_id": pid}

    # Fetch parent texts from ChromaDB
    parent_ids = list(best_per_parent.keys())
    
    if parent_ids:
        try:
            parent_data = parent_col.get(
                ids=parent_ids,
                include=["documents", "metadatas"],
            )
            # Map parent IDs to their texts
            parent_texts = dict(zip(parent_data["ids"], parent_data["documents"]))
            parent_metas = dict(zip(parent_data["ids"], parent_data["metadatas"]))
        except Exception:
            parent_texts = {}
            parent_metas = {}
    else:
        parent_texts = {}
        parent_metas = {}

    # Enrich candidates with parent text
    resolved = []
    for pid, candidate in best_per_parent.items():
        candidate["parent_text"] = parent_texts.get(pid, candidate["child_text"])
        candidate["parent_metadata"] = parent_metas.get(pid, candidate["metadata"])
        resolved.append(candidate)

    # Re-sort by combined score
    resolved.sort(key=lambda x: x.get("combined_score", 0.0), reverse=True)
    return resolved


# ===========================================================================
# Stage 3: Cross-Encoder Reranking
# ===========================================================================

def _rerank(query: str, candidates: list[dict], top_k: int = FINAL_TOP_K) -> list[dict]:
    """Rerank candidates using a cross-encoder model.
    
    The cross-encoder reads query + parent_text together (not independently)
    and produces a relevance score. This is much more accurate than embedding
    similarity for determining actual relevance.
    """
    if not candidates:
        return []

    cross_encoder = _get_cross_encoder()

    # Prepare input pairs: (query, parent_text)
    pairs = [(query, c["parent_text"]) for c in candidates]

    # Score all pairs
    scores = cross_encoder.predict(pairs)

    # Apply sigmoid to get scores in [0, 1] range
    import math
    for i, score in enumerate(scores):
        candidates[i]["rerank_score"] = 1.0 / (1.0 + math.exp(-float(score)))

    # Sort by rerank score
    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)

    return candidates[:top_k]


# ===========================================================================
# Main Search API
# ===========================================================================

def search(
    query: str,
    top_k: int = FINAL_TOP_K,
    use_reranker: bool = True,
    semantic_weight: float | None = None,
    bm25_weight: float | None = None,
    metadata_filter: dict | None = None,
    child_collection: str | None = None,
    parent_collection: str | None = None,
    bm25_index_path: str | None = None,
) -> list[dict]:
    """Execute the full hybrid retrieval pipeline.
    
    Args:
        query: The search query (natural language)
        top_k: Number of final results to return
        use_reranker: Whether to apply cross-encoder reranking (slower but more accurate)
        semantic_weight: Override default semantic weight (0-1). If None, uses
            query-adaptive weighting (boosts BM25 for spec/standards queries).
        bm25_weight: Override default BM25 weight (0-1)
        metadata_filter: Optional ChromaDB where clause for metadata filtering.
            Example: {"source": "REFERENCE-ISO-Cleanliness-Codes.md"}
            Example: {"section_header": {"$contains": "Beta"}}
        child_collection: Override the default ChromaDB child collection name.
        parent_collection: Override the default ChromaDB parent collection name.
        bm25_index_path: Override the default BM25 index file path.
    
    Returns:
        List of result dicts, each containing:
        - parent_text: the context chunk for the LLM
        - child_text: the matched child chunk
        - source: source filename
        - rerank_score: cross-encoder confidence
        - semantic_score: embedding similarity
        - bm25_score: keyword relevance
        - metadata: full chunk metadata
    """
    if VERBOSE:
        print(f"\n  Searching: \"{query}\"")

    # Determine weights: explicit override > query-adaptive > config defaults
    if semantic_weight is not None or bm25_weight is not None:
        sem_w = semantic_weight if semantic_weight is not None else SEMANTIC_WEIGHT
        bm25_w = bm25_weight if bm25_weight is not None else BM25_WEIGHT
    else:
        sem_w, bm25_w = _adaptive_weights(query)
    
    if VERBOSE and (sem_w != SEMANTIC_WEIGHT or bm25_w != BM25_WEIGHT):
        print(f"    Weights: semantic={sem_w:.2f}, bm25={bm25_w:.2f} (adaptive)")

    # Stage 1: Hybrid search
    if VERBOSE:
        print("  Stage 1: Hybrid search (semantic + BM25)...")
    
    semantic_hits = _semantic_search(query, where_filter=metadata_filter, child_collection=child_collection)
    bm25_hits = _bm25_search(query, metadata_filter=metadata_filter, bm25_index_path=bm25_index_path)

    if VERBOSE:
        print(f"    Semantic: {len(semantic_hits)} hits | BM25: {len(bm25_hits)} hits")

    candidates = _merge_results(
        semantic_hits, bm25_hits,
        semantic_weight=sem_w, bm25_weight=bm25_w,
    )

    if VERBOSE:
        both_count = sum(1 for c in candidates if c.get("source") == "both")
        print(f"    Merged (RRF): {len(candidates)} candidates ({both_count} found by both methods)")

    if not candidates:
        if VERBOSE:
            print("  [!] No results found.")
        return []

    # Stage 2: Resolve parents
    if VERBOSE:
        print("  Stage 2: Resolving parent chunks...")

    resolved = _resolve_parents(candidates, parent_collection=parent_collection)

    if VERBOSE:
        print(f"    Resolved to {len(resolved)} unique parent chunks")

    # Stage 3: Rerank
    if use_reranker:
        if VERBOSE:
            print("  Stage 3: Cross-encoder reranking...")

        results = _rerank(query, resolved, top_k)

        if VERBOSE:
            print(f"    Top score: {results[0]['rerank_score']:.3f}" if results else "    No results")
    else:
        results = resolved[:top_k]
        for r in results:
            r["rerank_score"] = r.get("combined_score", 0.0)

    # Clean up output format
    clean_results = []
    for r in results:
        clean_results.append({
            "parent_id": r.get("parent_id", r.get("child_id", "")),
            "parent_text": r.get("parent_text", ""),
            "child_text": r.get("child_text", ""),
            "source": r.get("metadata", {}).get("source", "unknown"),
            "rerank_score": round(r.get("rerank_score", 0.0), 4),
            "semantic_score": round(r.get("semantic_score", 0.0), 4),
            "bm25_score": round(r.get("bm25_score", 0.0), 4),
            "combined_score": round(r.get("combined_score", 0.0), 4),
            "metadata": r.get("metadata", {}),
            "parent_metadata": r.get("parent_metadata", {}),
        })

    return clean_results


# ===========================================================================
# CLI (for quick testing)
# ===========================================================================

def main():
    """Quick CLI for testing hybrid search."""
    import argparse

    parser = argparse.ArgumentParser(description="Hybrid search test")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results")
    parser.add_argument("--no-rerank", action="store_true", help="Skip cross-encoder reranking")
    parser.add_argument("--semantic-only", action="store_true", help="Use semantic search only")
    parser.add_argument("--bm25-only", action="store_true", help="Use BM25 keyword search only")

    args = parser.parse_args()

    if not args.query:
        parser.print_help()
        return

    # Handle search mode overrides
    kwargs = {"top_k": args.top_k, "use_reranker": not args.no_rerank}
    if args.semantic_only:
        kwargs["semantic_weight"] = 1.0
        kwargs["bm25_weight"] = 0.0
    elif args.bm25_only:
        kwargs["semantic_weight"] = 0.0
        kwargs["bm25_weight"] = 1.0

    results = search(args.query, **kwargs)

    if not results:
        print("\nNo results found.")
        return

    print(f"\n{'='*70}")
    print(f"RESULTS FOR: \"{args.query}\"  ({len(results)} results)")
    print(f"{'='*70}")

    for i, r in enumerate(results, 1):
        print(f"\n--- Result {i} ---")
        print(f"  Source:       {r['source']}")
        print(f"  Rerank score: {r['rerank_score']:.4f}")
        print(f"  Semantic:     {r['semantic_score']:.4f} | BM25: {r['bm25_score']:.4f} | Combined: {r['combined_score']:.4f}")
        print(f"  Child text:   {r['child_text'][:150]}...")
        print(f"  Parent text:  {r['parent_text'][:200]}...")

    print()


if __name__ == "__main__":
    main()
