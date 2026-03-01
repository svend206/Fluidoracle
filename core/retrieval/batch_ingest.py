from __future__ import annotations
"""
Fluidoracle — Batch Document Ingestion
================================================
Ingests all documents from a directory (and subdirectories) into the
knowledge base in one shot. Designed for bulk loading hundreds of files.

Features:
  - Recursively scans directories for supported file types
  - Tracks already-ingested files to avoid duplicates (via manifest)
  - Auto-tags based on filename and subdirectory
  - Skips and logs failures without stopping the batch
  - Rebuilds the BM25 index once at the end (not per-file)
  - Shows progress with estimated time remaining

Usage:
    python3.12 batch_ingest.py source-files/
    python3.12 batch_ingest.py source-files/ --collection reference --dry-run
    python3.12 batch_ingest.py source-files/ --force   (re-ingest everything)
    python3.12 batch_ingest.py --manifest               (show what's been ingested)
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Import the existing ingest pipeline
from .ingest import (
    load_document,
    create_parent_child_chunks,
    embed_texts,
    store_chunks,
    build_bm25_index,
    chroma_client,
)
from .config import (
    KNOWLEDGE_BASE_DIR,
    CHILD_COLLECTION,
    PARENT_COLLECTION,
    VERBOSE,
)


# ---------------------------------------------------------------------------
# Manifest — tracks what's already been ingested
# ---------------------------------------------------------------------------
MANIFEST_PATH = KNOWLEDGE_BASE_DIR / "ingest-manifest.jsonl"

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".md", ".txt", ".text", ".rst"}


def load_manifest() -> dict:
    """Load the ingestion manifest. Returns {filepath_hash: entry_dict}."""
    manifest = {}
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    manifest[entry["file_hash"]] = entry
    return manifest


def append_manifest(entry: dict):
    """Append an entry to the ingestion manifest."""
    with open(MANIFEST_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def file_hash(filepath: Path) -> str:
    """Hash file content for deduplication."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Auto-tagging
# ---------------------------------------------------------------------------

def auto_tags(filepath: Path, base_dir: Path) -> str:
    """Generate tags from the file's path and name.
    
    Examples:
        source-files/spraying-systems/catalog.pdf → "spraying-systems,catalog"
        source-files/atomization-papers/smith2024.pdf → "atomization-papers,smith2024"
    """
    tags = []

    # Add subdirectory names as tags (relative to base_dir)
    try:
        rel = filepath.relative_to(base_dir)
        for part in rel.parts[:-1]:  # directories, not the filename
            tag = part.lower().replace(" ", "-").replace("_", "-")
            if tag and tag != "source-files":
                tags.append(tag)
    except ValueError:
        pass

    # Add cleaned filename as a tag
    stem = filepath.stem.lower()
    stem = stem.replace(" ", "-").replace("_", "-")
    # Truncate very long filenames
    if len(stem) > 40:
        stem = stem[:40]
    tags.append(stem)

    return ",".join(tags)


# ---------------------------------------------------------------------------
# Batch Ingestion
# ---------------------------------------------------------------------------

def find_documents(directory: Path) -> list[Path]:
    """Recursively find all supported documents in a directory."""
    docs = []
    for ext in SUPPORTED_EXTENSIONS:
        docs.extend(directory.rglob(f"*{ext}"))
    # Sort for consistent ordering
    docs.sort(key=lambda p: p.name.lower())
    return docs


def ingest_single(
    filepath: Path,
    collection: str,
    tags: str,
    skip_bm25: bool = True,
) -> dict:
    """Ingest a single file. Returns a status dict.
    
    Args:
        skip_bm25: If True, don't rebuild BM25 after each file (for batch use).
    """
    filename = filepath.name
    result = {
        "file": str(filepath),
        "filename": filename,
        "status": "unknown",
        "parents": 0,
        "children": 0,
        "error": None,
    }

    try:
        # Load document
        text = load_document(str(filepath))

        if len(text) < 50:
            result["status"] = "skipped_empty"
            result["error"] = f"Document too short ({len(text)} chars)"
            return result

        # Create parent-child chunks
        parent_chunks, child_chunks = create_parent_child_chunks(text, filename)

        # Add collection and tag metadata
        for chunk in parent_chunks + child_chunks:
            chunk["metadata"]["collection_tag"] = collection
            chunk["metadata"]["tags"] = tags

        # Embed child chunks (use embed_text with contextual prefix when available)
        child_texts = [c.get("embed_text", c["text"]) for c in child_chunks]
        child_embeddings = embed_texts(child_texts)

        # Store in ChromaDB
        store_chunks(parent_chunks, PARENT_COLLECTION, embeddings=None)
        store_chunks(child_chunks, CHILD_COLLECTION, embeddings=child_embeddings)

        # Optionally rebuild BM25 (skip during batch, do once at end)
        if not skip_bm25:
            build_bm25_index()

        result["status"] = "success"
        result["parents"] = len(parent_chunks)
        result["children"] = len(child_chunks)
        result["chars"] = len(text)

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result


def batch_ingest(
    directory: Path,
    collection: str = "reference",
    force: bool = False,
    dry_run: bool = False,
):
    """Ingest all documents from a directory."""
    documents = find_documents(directory)

    if not documents:
        print(f"\nNo supported files found in: {directory}")
        print(f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        return

    manifest = load_manifest()

    # Determine what needs ingesting
    to_ingest = []
    skipped_existing = 0

    for doc in documents:
        fhash = file_hash(doc)
        if not force and fhash in manifest:
            skipped_existing += 1
            continue
        to_ingest.append((doc, fhash))

    # Report
    print(f"\n{'='*60}")
    print(f"  BATCH INGESTION")
    print(f"{'='*60}")
    print(f"  Directory:       {directory}")
    print(f"  Files found:     {len(documents)}")
    print(f"  Already ingested: {skipped_existing} (skipping)")
    print(f"  To ingest:       {len(to_ingest)}")
    print(f"  Collection:      {collection}")
    if force:
        print(f"  Mode:            FORCE (re-ingesting all)")
    if dry_run:
        print(f"  Mode:            DRY RUN (no changes)")
    print(f"{'='*60}\n")

    if dry_run:
        for doc, fhash in to_ingest:
            tags = auto_tags(doc, directory)
            print(f"  Would ingest: {doc.name}")
            print(f"    Tags: {tags}")
            print(f"    Hash: {fhash}")
            print()
        print(f"Dry run complete. {len(to_ingest)} files would be ingested.")
        return

    if not to_ingest:
        print("Nothing to ingest. Use --force to re-ingest everything.")
        return

    # Ingest each file
    results = {"success": 0, "error": 0, "skipped": 0}
    total_parents = 0
    total_children = 0
    errors = []
    start_time = time.time()

    for i, (doc, fhash) in enumerate(to_ingest, 1):
        tags = auto_tags(doc, directory)
        elapsed = time.time() - start_time
        rate = i / max(elapsed, 0.1)
        remaining = (len(to_ingest) - i) / max(rate, 0.01)

        print(f"  [{i}/{len(to_ingest)}] {doc.name}", end="", flush=True)
        if i > 1:
            print(f"  (~{int(remaining)}s remaining)", end="", flush=True)
        print()

        result = ingest_single(doc, collection, tags, skip_bm25=True)

        if result["status"] == "success":
            results["success"] += 1
            total_parents += result["parents"]
            total_children += result["children"]

            # Record in manifest
            append_manifest({
                "file_hash": fhash,
                "filename": result["filename"],
                "filepath": str(doc),
                "collection": collection,
                "tags": tags,
                "parents": result["parents"],
                "children": result["children"],
                "chars": result.get("chars", 0),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            })

            print(f"           ✓ {result['parents']} parents, {result['children']} children")

        elif result["status"] == "skipped_empty":
            results["skipped"] += 1
            print(f"           ⊘ Skipped: {result['error']}")

        else:
            results["error"] += 1
            errors.append(result)
            print(f"           ✗ Error: {result['error']}")

    # Rebuild BM25 index once at the end
    if results["success"] > 0:
        print(f"\n  Rebuilding BM25 keyword index...")
        try:
            build_bm25_index()
            print(f"  ✓ BM25 index rebuilt")
        except Exception as e:
            print(f"  ✗ BM25 rebuild failed: {e}")

    # Summary
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  BATCH COMPLETE")
    print(f"{'='*60}")
    print(f"  Successful:   {results['success']}")
    print(f"  Skipped:      {results['skipped']}")
    print(f"  Errors:       {results['error']}")
    print(f"  Total chunks: {total_parents} parents, {total_children} children")
    print(f"  Time:         {elapsed:.1f}s ({elapsed/max(len(to_ingest),1):.1f}s per file)")
    print(f"{'='*60}\n")

    if errors:
        print("  Failed files:")
        for e in errors:
            print(f"    ✗ {e['filename']}: {e['error']}")
        print()


def show_manifest():
    """Display the ingestion manifest."""
    manifest = load_manifest()

    if not manifest:
        print("\nNo files have been ingested yet.")
        return

    print(f"\n{'='*60}")
    print(f"  INGESTION MANIFEST ({len(manifest)} files)")
    print(f"{'='*60}\n")

    total_parents = 0
    total_children = 0
    total_chars = 0

    for fhash, entry in sorted(manifest.items(), key=lambda x: x[1].get("ingested_at", "")):
        parents = entry.get("parents", 0)
        children = entry.get("children", 0)
        chars = entry.get("chars", 0)
        total_parents += parents
        total_children += children
        total_chars += chars

        print(f"  {entry['filename']}")
        print(f"    Collection: {entry.get('collection', 'unknown')} | Tags: {entry.get('tags', '')}")
        print(f"    Chunks: {parents}p / {children}c | Chars: {chars:,}")
        print(f"    Ingested: {entry.get('ingested_at', 'unknown')[:10]}")
        print()

    print(f"  Totals: {total_parents} parents, {total_children} children, {total_chars:,} chars")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Batch ingest documents into the hydraulic filter knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3.12 batch_ingest.py source-files/
  python3.12 batch_ingest.py source-files/ --collection reference --dry-run
  python3.12 batch_ingest.py source-files/ --force
  python3.12 batch_ingest.py --manifest
        """,
    )
    parser.add_argument("directory", nargs="?", help="Directory containing documents to ingest")
    parser.add_argument("--collection", default="reference", help="Collection tag (default: reference)")
    parser.add_argument("--force", action="store_true", help="Re-ingest files even if already in manifest")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be ingested without doing it")
    parser.add_argument("--manifest", action="store_true", help="Show ingestion manifest")

    args = parser.parse_args()

    if args.manifest:
        show_manifest()
    elif args.directory:
        directory = Path(args.directory)
        if not directory.exists():
            print(f"Directory not found: {directory}")
            sys.exit(1)
        if not directory.is_dir():
            print(f"Not a directory: {directory}")
            sys.exit(1)
        batch_ingest(
            directory=directory,
            collection=args.collection,
            force=args.force,
            dry_run=args.dry_run,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
