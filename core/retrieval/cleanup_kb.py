"""
Knowledge Base Cleanup — Remove non-hydraulic-filter content
=========================================================
Removes irrelevant documents from the ChromaDB vector store:
  - MIT 18.03 Differential Equations courseware (~543 files)
  - Irrelevant textbooks (calculus, statistics, general physics)
  - Off-topic research papers (additive manufacturing, ML, fire dynamics, etc.)
  - Non-hydraulic-filter product catalogs (Danfoss refrigeration)
  - Miscellaneous files (robots.txt, etc.)

After removal, rebuilds the BM25 index.

Usage:
    python cleanup_kb.py --dry-run    # Preview what would be removed
    python cleanup_kb.py --execute    # Actually remove and rebuild BM25
"""

import re
import sys
import time
from pathlib import Path

# Ensure we can import config and ingest
sys.path.insert(0, str(Path(__file__).parent))

import chromadb
from .config import (
    VECTOR_STORE_PATH,
    CHILD_COLLECTION,
    PARENT_COLLECTION,
)


# ===========================================================================
# Removal patterns
# ===========================================================================

# Regex patterns — any source filename matching these gets removed
REMOVE_PATTERNS = [
    r"MIT18_03",           # MIT 18.03 ODE courseware (521+ files)
    r"MIT18_098",          # MIT 18.098 IAP supplementary
    r"_pset\d+\.pdf$",     # MIT problem sets with hash prefixes
    r"_soln\d+\.pdf$",     # MIT solutions with hash prefixes
    r"_finals\.pdf$",      # MIT final exams
    r"_toc\.pdf$",         # Table of contents files
    r"_topics\.pdf$",      # MIT topics files
    r"_logarithms\.pdf$",  # MIT logarithm supplement
    r"_sf_math\.pdf$",     # MIT supplementary math
    r"_feedback\.pdf$",    # MIT course feedback
    r"_3q\.pdf$",          # MIT quiz files
    r"_2qa\.pdf$",         # MIT quiz files
    r"_3qa\.pdf$",         # MIT quiz files
]

# Exact filenames to remove
REMOVE_EXACT = {
    # Calculus textbooks
    "Calculus_Volume_1_-_WEB_l4sAIKd.pdf",
    "Calculus_Volume_2_-_WEB.pdf",
    "Calculus_Volume_3_-_WEB.pdf",
    "Strang Calculus.pdf",
    # Statistics textbook
    "Introductory_Statistics_2e_-_WEB.pdf",
    # General physics textbooks
    "university-physics-vol1.pdf",
    "university-physics-vol2.pdf",
    "university-physics-vol3.pdf",
    # Misc
    "robots.txt",

    # --- Off-topic research papers (not hydraulic-filter related) ---

    # Fire dynamics CFD software manual — not hydraulic filter content
    "McGrattan2007_Fire-dynamics-simulator-version-5.pdf",
    # Machine learning in solid-state materials science — no spray relevance
    "Schmidt2019_Recent-advances-and-applications-of-machine-learni.pdf",
    # Printed sensors/electronics on flexible substrates — not spray related
    "Lee2014_Technologies-for-Printing-Sensors-and-Electronics.pdf",
    # Directed Energy Deposition (additive manufacturing) — not hydraulic filters
    "Ahn2021_Directed-Energy-Deposition-DED-Process-State-of-th.pdf",
    # Additive manufacturing methods review — not hydraulic filters
    "Bikas2015_Additive-manufacturing-methods-and-modelling-appro.pdf",
    # Additive manufacturing textbook — not hydraulic filters
    "Gibson2009_Additive-Manufacturing-Technologies.pdf",
    # Metal additive manufacturing review — not hydraulic filters
    "Frazier2014_Metal-Additive-Manufacturing-A-Review.pdf",
    # Metallic additive manufacturing review — not hydraulic filters
    "Zhang2017_Additive-Manufacturing-of-Metallic-Materials-A-Rev.pdf",
    # Lean premixed prevaporized combustion thesis — combustion, not hydraulic filters
    "Charest2005_Design-methodology-for-a-lean-premixed-prevaporize.pdf",
    # Danfoss refrigeration/HVAC component catalog — not hydraulic filters at all
    "AF371473195263en-010602.pdf",
}

# Patterns for exact-suffix matches with hash-prefixed MIT supplementary files
REMOVE_HASH_SUFFIXES = [
    "pset01.pdf", "pset02.pdf", "pset03.pdf", "pset04.pdf",
    "pset05.pdf", "pset06.pdf", "pset07.pdf", "pset08.pdf",
    "pset09.pdf", "pset10.pdf",
    "soln01.pdf", "soln02.pdf", "soln03.pdf", "soln04.pdf",
    "soln05.pdf", "soln06.pdf", "soln07.pdf", "soln08.pdf",
    "soln09.pdf", "soln10.pdf",
]


def should_remove(source_filename: str) -> str | None:
    """Check if a source should be removed. Returns the reason, or None if it should stay."""
    # Check exact matches
    if source_filename in REMOVE_EXACT:
        return f"exact: {source_filename}"

    # Check regex patterns
    for pattern in REMOVE_PATTERNS:
        if re.search(pattern, source_filename):
            return f"pattern: {pattern}"

    # Check hash-prefixed MIT supplementary files
    for suffix in REMOVE_HASH_SUFFIXES:
        if source_filename.endswith(f"_{suffix}"):
            return f"hash-MIT: {suffix}"

    return None


def get_unique_sources(collection) -> set[str]:
    """Get all unique source filenames from a collection (memory-efficient — only stores names, not IDs)."""
    import gc
    total = collection.count()
    sources = set()
    batch_size = 200  # Small batches to avoid OOM on constrained containers
    offset = 0

    while offset < total:
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["metadatas"],
        )
        if not batch["ids"]:
            break
        for meta in batch["metadatas"]:
            if meta and "source" in meta:
                sources.add(meta["source"])
        offset += batch_size
        del batch
        gc.collect()
        if offset % 2000 == 0:
            print(f"  Scanned {offset:,}/{total:,}... ({len(sources)} unique sources)")

    return sources


def delete_source(collection, source_name: str) -> int:
    """Delete all chunks for a given source from a collection. Returns count deleted."""
    # Use ChromaDB where filter to find and delete by source metadata
    # We need to get IDs first since ChromaDB delete needs IDs
    deleted = 0
    while True:
        batch = collection.get(
            where={"source": source_name},
            limit=500,
            include=[],  # Don't load documents/embeddings — just IDs
        )
        if not batch["ids"]:
            break
        collection.delete(ids=batch["ids"])
        deleted += len(batch["ids"])
    return deleted


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clean up knowledge base")
    parser.add_argument("--dry-run", action="store_true", help="Preview removals without executing")
    parser.add_argument("--execute", action="store_true", help="Execute removals")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Please specify --dry-run or --execute")
        sys.exit(1)

    client = chromadb.PersistentClient(path=str(VECTOR_STORE_PATH))
    children = client.get_collection(CHILD_COLLECTION)
    parents = client.get_collection(PARENT_COLLECTION)

    child_count = children.count()
    parent_count = parents.count()
    print(f"Current counts — Children: {child_count:,}, Parents: {parent_count:,}")
    print()

    # Get unique source names from parent collection only (much smaller scan)
    print("Scanning parent collection for unique source names...")
    all_sources = get_unique_sources(parents)
    print(f"  Found {len(all_sources)} unique sources")
    print()

    # Identify sources to remove
    to_remove: dict[str, str] = {}  # source -> reason
    for source in all_sources:
        reason = should_remove(source)
        if reason:
            to_remove[source] = reason

    print(f"=== REMOVAL SUMMARY ===")
    print(f"Sources to remove: {len(to_remove)} out of {len(all_sources)} total")
    print(f"Sources to keep: {len(all_sources) - len(to_remove)}")
    print()

    # Group by reason for readability
    by_reason: dict[str, int] = {}
    for reason in to_remove.values():
        # Simplify reason for grouping
        key = reason.split(":")[0].strip()
        by_reason[key] = by_reason.get(key, 0) + 1

    for reason, count in sorted(by_reason.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count} files")
    print()

    # Show a few examples
    print("Sample sources being removed:")
    for source, reason in list(sorted(to_remove.items()))[:10]:
        print(f"  ✗ {source}  ({reason})")
    if len(to_remove) > 10:
        print(f"  ... and {len(to_remove) - 10} more")
    print()

    print("Sample sources being KEPT:")
    kept = sorted(s for s in all_sources if s not in to_remove)
    for source in kept[:10]:
        print(f"  ✓ {source}")
    print(f"  ... and {len(kept) - 10} more")
    print()

    if args.dry_run:
        print("DRY RUN — no changes made. Use --execute to proceed.")
        return

    # === EXECUTE REMOVAL ===
    print("=" * 60)
    print("EXECUTING REMOVAL...")
    print("=" * 60)
    t_start = time.time()

    total_parent_deleted = 0
    total_child_deleted = 0

    for i, source in enumerate(sorted(to_remove.keys()), 1):
        p_del = delete_source(parents, source)
        c_del = delete_source(children, source)
        total_parent_deleted += p_del
        total_child_deleted += c_del

        if i % 25 == 0 or i == len(to_remove):
            print(f"  Progress: {i}/{len(to_remove)} sources deleted "
                  f"({total_parent_deleted:,}p + {total_child_deleted:,}c chunks)")

    t_delete = time.time()
    print()
    print(f"Deletion complete in {t_delete - t_start:.1f}s")
    print(f"  Removed: {total_parent_deleted:,} parent + {total_child_deleted:,} child chunks")
    print(f"  Remaining: Children={children.count():,}, Parents={parents.count():,}")
    print()

    # Rebuild BM25 index
    print("Rebuilding BM25 index (this may take a few minutes)...")
    from ingest import build_bm25_index
    build_bm25_index()
    t_bm25 = time.time()
    print(f"BM25 rebuild complete in {t_bm25 - t_delete:.1f}s")
    print()

    print(f"=== CLEANUP COMPLETE ===")
    print(f"Total time: {t_bm25 - t_start:.1f}s")
    print(f"Final counts — Children: {children.count():,}, Parents: {parents.count():,}")


if __name__ == "__main__":
    main()
