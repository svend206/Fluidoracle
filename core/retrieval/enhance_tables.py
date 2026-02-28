from __future__ import annotations
"""
Table Enhancement — Make performance data tables discoverable
================================================================
Problem: ~20% of parent chunks are numeric tables (flow rates, pressure data,
spray angles, etc.). Their child chunks embed as essentially random vectors
because semantic models can't interpret raw numbers. These chunks contain
critical engineering data but are invisible to search.

Solution: For each table-heavy parent, create an "index child" — a new child
chunk containing a natural language description of what the table contains.
This description embeds well and makes the table discoverable via semantic
search. When the index child matches, parent resolution fetches the actual
table data for the LLM.

The description is built from:
  1. Source filename → product/catalog name
  2. Tags metadata → category
  3. Preceding parent chunks → product description, applications, headers
  4. Table chunk text → any column headers or labels found inline

After creating index children, rebuilds the BM25 index.

Usage:
    python enhance_tables.py --dry-run    # Preview what would be created
    python enhance_tables.py --execute    # Create index children + rebuild BM25
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import chromadb
from .config import (
    VECTOR_STORE_PATH,
    CHILD_COLLECTION,
    PARENT_COLLECTION,
)

# Threshold: parent chunks with alpha ratio below this are "table-heavy"
TABLE_ALPHA_THRESHOLD = 0.25

# How many preceding parents to read for context
CONTEXT_LOOKBACK = 3


# ---------------------------------------------------------------------------
# Filename → human-readable product name
# ---------------------------------------------------------------------------

def humanize_source(filename: str) -> str:
    """Convert a source filename into a human-readable product/document name.
    
    Uses manufacturer detection from verified_query (which loads patterns
    from oracle.db) to identify vendor documents. Falls back to generic
    cleanup for unrecognized filenames.
    """
    name = filename.rsplit(".", 1)[0]  # strip extension

    # Try to detect vendor via the database-backed vendor detection
    try:
        from verified_query import _detect_vendor
        vendor = _detect_vendor(filename)
        if vendor:
            # Strip vendor-like prefixes from the display name
            display = name.replace("_", " ").replace("-", " ").strip()
            # Remove the vendor name itself from the display if it starts with it
            for prefix in (vendor.lower(), vendor.split()[0].lower()):
                if display.lower().startswith(prefix):
                    display = display[len(prefix):].strip()
            if display:
                display = display[0].upper() + display[1:]
                return f"{vendor} — {display}"
            return vendor
    except ImportError:
        pass

    # Research papers: Author####_Title
    if re.match(r"[A-Z][a-z]+\d{4}_", name):
        parts = name.split("_", 1)
        if len(parts) > 1:
            title = parts[1].replace("-", " ").replace("_", " ")
            return f"Research Paper: {title} ({parts[0]})"
        return f"Research Paper ({parts[0]})"

    # Conference papers
    if name.lower().startswith("ilass") or name.lower().startswith("iclass"):
        return f"Conference Paper: {name.replace('_', ' ').replace('-', ' ')}"

    # Generic fallback
    return name.replace("_", " ").replace("-", " ").title()


def extract_headers_from_table(text: str) -> list[str]:
    """Extract any header/label text from a table-heavy chunk."""
    headers = []
    lines = text.split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Lines that are mostly alpha are likely headers
        alpha = sum(1 for c in stripped if c.isalpha())
        if len(stripped) > 3 and alpha / len(stripped) > 0.5:
            # Skip very short fragments that are just units
            if len(stripped) > 5:
                headers.append(stripped)
    return headers[:10]  # cap at 10 headers


def extract_context_from_preceding(preceding_texts: list[str]) -> str:
    """Extract useful context from preceding parent chunks.

    Looks for product descriptions, application lists, and section headers.
    Returns a condensed context string.
    """
    context_parts = []

    for text in preceding_texts:
        if not text:
            continue

        # Extract lines with good text content
        lines = text.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped or len(stripped) < 10:
                continue

            alpha = sum(1 for c in stripped if c.isalpha())
            ratio = alpha / len(stripped) if stripped else 0

            # Keep lines that are mostly text (descriptions, headers, applications)
            if ratio > 0.5 and len(stripped) > 15:
                # Skip boilerplate
                lower = stripped.lower()
                if any(skip in lower for skip in [
                    "spray.com", "1.800.95.spray", "intl. tel",
                    "copyright", "all rights reserved", "visit www",
                ]):
                    continue
                context_parts.append(stripped)

    return " ".join(context_parts[:15])  # first 15 useful lines


def build_table_description(
    source: str,
    tags: str,
    table_text: str,
    preceding_texts: list[str],
    parent_index: int,
) -> str:
    """Build a natural language description for a table-heavy chunk."""

    product_name = humanize_source(source)
    headers = extract_headers_from_table(table_text)
    context = extract_context_from_preceding(preceding_texts)

    # Build the description
    parts = [f"Performance data table from: {product_name}."]

    if headers:
        header_text = "; ".join(headers[:5])
        parts.append(f"Table headers and labels: {header_text}.")

    if context:
        # Trim context to a reasonable length
        if len(context) > 400:
            context = context[:400].rsplit(" ", 1)[0] + "..."
        parts.append(f"Context: {context}")

    # Add tag-based category info
    if tags:
        tag_parts = tags.split(",")
        if len(tag_parts) >= 2:
            category = tag_parts[0].replace("-", " ").title()
            parts.append(f"Category: {category}.")

    description = " ".join(parts)

    # Ensure it's within child chunk size limits (400 chars target)
    if len(description) > 600:
        description = description[:600].rsplit(" ", 1)[0] + "..."

    return description


def alpha_ratio(text: str) -> float:
    """Calculate the ratio of alphabetic characters in text."""
    if not text:
        return 0.0
    alpha_chars = sum(1 for c in text if c.isalpha())
    return alpha_chars / len(text)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Enhance table chunks with index children")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be created")
    parser.add_argument("--execute", action="store_true", help="Create index children + rebuild BM25")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Please specify --dry-run or --execute")
        sys.exit(1)

    client = chromadb.PersistentClient(path=str(VECTOR_STORE_PATH))
    parents = client.get_collection(PARENT_COLLECTION)
    children = client.get_collection(CHILD_COLLECTION)

    total_parents = parents.count()
    total_children = children.count()
    print(f"Current counts — Parents: {total_parents:,}, Children: {total_children:,}")
    print()

    # -----------------------------------------------------------------------
    # Pass 1: Identify table-heavy parents and gather context
    # -----------------------------------------------------------------------
    print("Pass 1: Scanning for table-heavy parents...")
    batch_size = 500

    # Build source → sorted list of (parent_index, alpha_ratio, text, metadata)
    source_parents: dict[str, list] = {}
    table_parent_count = 0

    for offset in range(0, total_parents, batch_size):
        batch = parents.get(include=["metadatas", "documents"], limit=batch_size, offset=offset)
        for meta, doc in zip(batch["metadatas"], batch["documents"]):
            src = meta["source"]
            pidx = meta["parent_index"]
            text = (doc or "").strip()
            ar = alpha_ratio(text)

            if src not in source_parents:
                source_parents[src] = []
            source_parents[src].append({
                "parent_index": pidx,
                "alpha_ratio": ar,
                "text": text,
                "metadata": meta,
                "is_table": ar < TABLE_ALPHA_THRESHOLD,
            })

        if (offset + batch_size) % 2000 == 0:
            print(f"  Scanned {min(offset + batch_size, total_parents):,}/{total_parents:,}...")

    # Sort each source's parents by index
    for src in source_parents:
        source_parents[src].sort(key=lambda x: x["parent_index"])

    # Count table parents
    for src, plist in source_parents.items():
        table_parent_count += sum(1 for p in plist if p["is_table"])

    print(f"  Found {table_parent_count} table-heavy parents (alpha < {TABLE_ALPHA_THRESHOLD})")
    print(f"  Across {len(source_parents)} unique sources")
    print()

    # -----------------------------------------------------------------------
    # Pass 2: Build descriptions for each table-heavy parent
    # -----------------------------------------------------------------------
    print("Pass 2: Building descriptions...")
    index_children = []  # list of {id, text, metadata}

    for src, plist in source_parents.items():
        for i, parent in enumerate(plist):
            if not parent["is_table"]:
                continue

            pidx = parent["parent_index"]
            tags = parent["metadata"].get("tags", "")

            # Gather preceding context (text-rich parents before this one)
            preceding_texts = []
            for j in range(max(0, i - CONTEXT_LOOKBACK), i):
                prev = plist[j]
                if prev["alpha_ratio"] > 0.3:
                    preceding_texts.append(prev["text"])

            # If no preceding text, try the first parent of this source
            if not preceding_texts and plist[0]["alpha_ratio"] > 0.3:
                preceding_texts.append(plist[0]["text"])

            description = build_table_description(
                source=src,
                tags=tags,
                table_text=parent["text"],
                preceding_texts=preceding_texts,
                parent_index=pidx,
            )

            parent_id = f"{src}::parent::{pidx}"
            child_id = f"{src}::child::{pidx}::idx"

            index_children.append({
                "id": child_id,
                "text": description,
                "metadata": {
                    "source": src,
                    "chunk_type": "child",
                    "parent_id": parent_id,
                    "parent_index": pidx,
                    "child_index": -1,  # sentinel: this is an index child
                    "char_count": len(description),
                    "tags": tags,
                    "collection_tag": parent["metadata"].get("collection_tag", "reference"),
                    "is_table_index": True,
                },
            })

    print(f"  Generated {len(index_children)} index children")
    print()

    # -----------------------------------------------------------------------
    # Preview / Execute
    # -----------------------------------------------------------------------
    if args.dry_run:
        print("=== DRY RUN — Sample descriptions ===")
        # Show samples from different sources
        shown_sources = set()
        shown = 0
        for ic in index_children:
            src = ic["metadata"]["source"]
            if src not in shown_sources and shown < 10:
                print(f"\n  Source: {src}")
                print(f"  Parent index: {ic['metadata']['parent_index']}")
                print(f"  Description ({len(ic['text'])} chars):")
                print(f"    {ic['text'][:500]}")
                shown_sources.add(src)
                shown += 1

        print(f"\n\nDRY RUN — {len(index_children)} index children would be created.")
        print("Use --execute to proceed.")
        return

    # === EXECUTE ===
    print("=" * 60)
    print("EXECUTING TABLE ENHANCEMENT...")
    print("=" * 60)
    t_start = time.time()

    # Step 1: Check for existing index children and remove them
    print("\nStep 1: Removing any existing index children...")
    existing_idx_ids = []
    for offset in range(0, total_children, 1000):
        batch = children.get(include=["metadatas"], limit=1000, offset=offset)
        for id_, meta in zip(batch["ids"], batch["metadatas"]):
            if meta.get("is_table_index"):
                existing_idx_ids.append(id_)

    if existing_idx_ids:
        for i in range(0, len(existing_idx_ids), 500):
            children.delete(ids=existing_idx_ids[i:i + 500])
        print(f"  Removed {len(existing_idx_ids)} existing index children")
    else:
        print("  No existing index children found")

    # Step 2: Generate embeddings for new index children
    print(f"\nStep 2: Generating embeddings for {len(index_children)} index children...")
    from ingest import embed_texts

    texts = [ic["text"] for ic in index_children]
    embeddings = embed_texts(texts, batch_size=100)
    t_embed = time.time()
    print(f"  Embeddings generated in {t_embed - t_start:.1f}s")

    # Step 3: Store in ChromaDB
    print("\nStep 3: Storing index children in ChromaDB...")
    ids = [ic["id"] for ic in index_children]
    documents = texts
    metadatas = [ic["metadata"] for ic in index_children]

    # Ensure metadata values are ChromaDB-compatible
    for meta in metadatas:
        for key, value in list(meta.items()):
            if isinstance(value, bool):
                meta[key] = str(value).lower()
            elif not isinstance(value, (str, int, float)):
                meta[key] = str(value)

    batch_store = 500
    for i in range(0, len(ids), batch_store):
        children.upsert(
            ids=ids[i:i + batch_store],
            documents=documents[i:i + batch_store],
            metadatas=metadatas[i:i + batch_store],
            embeddings=embeddings[i:i + batch_store],
        )
    t_store = time.time()
    print(f"  Stored {len(ids)} index children in {t_store - t_embed:.1f}s")

    # Step 4: Rebuild BM25 index
    print("\nStep 4: Rebuilding BM25 index...")
    from ingest import build_bm25_index
    build_bm25_index()
    t_bm25 = time.time()
    print(f"  BM25 rebuild complete in {t_bm25 - t_store:.1f}s")

    # Summary
    print()
    print(f"=== ENHANCEMENT COMPLETE ===")
    print(f"Total time: {t_bm25 - t_start:.1f}s")
    print(f"Index children created: {len(index_children)}")
    print(f"Final counts — Parents: {parents.count():,}, Children: {children.count():,}")


if __name__ == "__main__":
    main()
