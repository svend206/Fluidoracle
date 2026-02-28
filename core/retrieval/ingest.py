from __future__ import annotations

"""
Hydraulic Filter Expert — Document Ingestion Pipeline (v2: Parent-Child + BM25)
===========================================================================
Ingests documents into the knowledge base using a two-level chunking strategy:

  1. PARENT chunks (~2000 chars) — stored for context delivery to the LLM.
     When the agent retrieves knowledge, it gets these larger chunks so it
     has enough surrounding context to answer accurately.

  2. CHILD chunks (~400 chars) — stored for search precision. These are what
     get matched against the user's query. Each child maps to a parent.

Additionally builds a BM25 keyword index alongside the vector store so that
exact term matches (model numbers, technical codes) are found even when
semantic similarity fails.

Usage:
    py -3.12 ingest.py "path/to/document.pdf" --collection reference --tags "spray-systems,general"
    py -3.12 ingest.py --status
    py -3.12 ingest.py --rebuild-bm25
"""

import argparse
import hashlib
import json
import pickle
import re
import sys
import time
import uuid
from pathlib import Path

import chromadb
from openai import OpenAI

from .config import (
    OPENAI_API_KEY,
    EMBEDDING_MODEL,
    VECTOR_STORE_PATH,
    BM25_INDEX_PATH,
    CHILD_COLLECTION,
    PARENT_COLLECTION,
    PARENT_CHUNK_SIZE,
    PARENT_CHUNK_OVERLAP,
    CHILD_CHUNK_SIZE,
    CHILD_CHUNK_OVERLAP,
    VERBOSE,
)

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
openai_client = OpenAI(api_key=OPENAI_API_KEY)
chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_PATH))


# ===========================================================================
# Document Loading
# ===========================================================================

def load_document(filepath: str) -> str:
    """Load text content from a file. Supports PDF, DOCX, MD, TXT."""
    path = Path(filepath)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix == ".docx":
        from docx import Document
        doc = Document(str(path))
        text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    elif suffix in (".md", ".txt", ".text", ".rst"):
        text = path.read_text(encoding="utf-8", errors="replace")
    else:
        print(f"[!] Unsupported file type: {suffix}")
        sys.exit(1)

    # Basic cleanup
    text = re.sub(r"\n{3,}", "\n\n", text)       # collapse excessive newlines
    text = re.sub(r"[ \t]{2,}", " ", text)        # collapse excessive spaces
    return text.strip()


# ===========================================================================
# Parent-Child Chunking
# ===========================================================================

# Maximum parent chunk size — sections longer than this get split further
MAX_PARENT_CHUNK_SIZE = 4000

def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks of approximately chunk_size characters.
    
    Tries to split at paragraph or sentence boundaries when possible to
    avoid cutting mid-sentence.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Try to find a good break point (paragraph > sentence > word)
        candidate = text[start:end]

        # Look for paragraph break in the last 20% of the chunk
        search_zone = candidate[int(chunk_size * 0.8):]
        para_break = search_zone.rfind("\n\n")
        if para_break != -1:
            end = start + int(chunk_size * 0.8) + para_break + 2
        else:
            # Look for sentence break
            sent_break = max(
                search_zone.rfind(". "),
                search_zone.rfind(".\n"),
                search_zone.rfind("? "),
                search_zone.rfind("! "),
            )
            if sent_break != -1:
                end = start + int(chunk_size * 0.8) + sent_break + 2
            else:
                # Fall back to word boundary
                word_break = candidate.rfind(" ")
                if word_break > chunk_size * 0.5:
                    end = start + word_break + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks


def _split_markdown_sections(text: str) -> list[dict]:
    """Split markdown text at ## and ### header boundaries.
    
    Returns a list of dicts:
        {"header": str or None, "body": str}
    
    Sections longer than MAX_PARENT_CHUNK_SIZE are sub-split using
    the standard chunk_text() character-based splitter.
    """
    # Match lines starting with ## or ### (not # which is the doc title)
    header_pattern = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
    
    sections = []
    matches = list(header_pattern.finditer(text))
    
    if not matches:
        # No markdown headers — return the whole text as one section
        return [{"header": None, "body": text.strip()}]
    
    # Content before the first header (preamble)
    preamble = text[:matches[0].start()].strip()
    if preamble:
        sections.append({"header": None, "body": preamble})
    
    # Each header starts a section that runs until the next header
    for i, match in enumerate(matches):
        header = match.group(2).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        
        sections.append({"header": header, "body": body})
    
    return sections


def create_parent_child_chunks(text: str, source_filename: str) -> tuple[list[dict], list[dict]]:
    """Create two-level chunks: parents for context, children for search.
    
    For markdown files (.md), splits at section header boundaries first,
    preserving document structure. Each section becomes a parent chunk.
    Sections exceeding MAX_PARENT_CHUNK_SIZE are sub-split.
    
    For non-markdown files, uses character-based splitting as before.
    
    Child chunks always get a contextual prefix prepended to their text
    before embedding, so the embedding carries document and section context.
    The prefix is stored in metadata (not in the child text itself) and
    is applied during embedding generation.
    
    Returns:
        (parent_chunks, child_chunks) where each chunk is a dict with:
        - id: unique identifier
        - text: the chunk content
        - metadata: source info and relationships
    """
    is_markdown = source_filename.lower().endswith((".md", ".markdown"))
    
    if is_markdown:
        parent_texts_with_headers = _create_markdown_parents(text, source_filename)
    else:
        # Non-markdown: character-based splitting (original behavior)
        raw_parents = chunk_text(text, PARENT_CHUNK_SIZE, PARENT_CHUNK_OVERLAP)
        parent_texts_with_headers = [(t, None) for t in raw_parents]
    
    parent_chunks = []
    child_chunks = []

    for p_idx, (parent_text, section_header) in enumerate(parent_texts_with_headers):
        parent_id = f"{source_filename}::parent::{p_idx}"

        parent_meta = {
            "source": source_filename,
            "chunk_type": "parent",
            "parent_index": p_idx,
            "char_count": len(parent_text),
        }
        if section_header:
            parent_meta["section_header"] = section_header

        parent_chunks.append({
            "id": parent_id,
            "text": parent_text,
            "metadata": parent_meta,
        })

        # Build contextual prefix for child embeddings
        context_prefix = f"Document: {source_filename}"
        if section_header:
            context_prefix += f" | Section: {section_header}"
        context_prefix += " | "

        # Split parent into child chunks
        child_texts = chunk_text(parent_text, CHILD_CHUNK_SIZE, CHILD_CHUNK_OVERLAP)

        for c_idx, child_text in enumerate(child_texts):
            child_id = f"{source_filename}::child::{p_idx}::{c_idx}"

            child_chunks.append({
                "id": child_id,
                "text": child_text,
                # embed_text has the contextual prefix for embedding generation;
                # the stored "text" in ChromaDB remains the raw chunk for display.
                "embed_text": context_prefix + child_text,
                "metadata": {
                    "source": source_filename,
                    "chunk_type": "child",
                    "parent_id": parent_id,
                    "parent_index": p_idx,
                    "child_index": c_idx,
                    "char_count": len(child_text),
                    "section_header": section_header or "",
                    "context_prefix": context_prefix,
                }
            })

    return parent_chunks, child_chunks


def _create_markdown_parents(text: str, source_filename: str) -> list[tuple[str, str | None]]:
    """Split markdown into section-based parent chunks.
    
    Returns list of (parent_text, section_header) tuples.
    Sections longer than MAX_PARENT_CHUNK_SIZE are sub-split using
    character-based chunking while preserving the section header.
    """
    sections = _split_markdown_sections(text)
    parents = []
    
    for section in sections:
        body = section["body"]
        header = section["header"]
        
        if len(body) <= MAX_PARENT_CHUNK_SIZE:
            parents.append((body, header))
        else:
            # Section too long — sub-split with character-based chunking
            sub_chunks = chunk_text(body, PARENT_CHUNK_SIZE, PARENT_CHUNK_OVERLAP)
            for sub in sub_chunks:
                parents.append((sub, header))
    
    return parents


# ===========================================================================
# Embedding
# ===========================================================================

def embed_texts(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """Generate embeddings for a list of texts using OpenAI API.
    
    Processes in batches to stay within API limits.
    """
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        if VERBOSE:
            print(f"  Embedding batch {i // batch_size + 1} ({len(batch)} chunks)...")

        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
        time.sleep(0.1)  # gentle rate limiting

    return all_embeddings


# ===========================================================================
# BM25 Index Management
# ===========================================================================

def tokenize_for_bm25(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer for BM25.
    
    Keeps technical terms intact (model numbers, codes with slashes/dashes).
    Lowercases everything for matching.
    """
    # Split on whitespace, keep alphanumeric + common technical punctuation
    tokens = re.findall(r"[a-zA-Z0-9][\w/\-\.]*[a-zA-Z0-9]|[a-zA-Z0-9]", text.lower())
    return tokens


def build_bm25_index(
    child_collection_name: str = CHILD_COLLECTION,
    bm25_output_path: str | Path | None = None,
):
    """Build (or rebuild) the BM25 keyword index from all child chunks in ChromaDB.

    Args:
        child_collection_name: ChromaDB collection to index.
        bm25_output_path: Where to save the pickle. Defaults to BM25_INDEX_PATH / "bm25_index.pkl".
    """
    from rank_bm25 import BM25Okapi

    collection = chroma_client.get_collection(name=child_collection_name)
    total = collection.count()

    if total == 0:
        print("[!] No child chunks found in ChromaDB. Ingest documents first.")
        return

    # Paginate to avoid "too many SQL variables" error on large collections
    ids = []
    documents = []
    metadatas = []
    batch_size = 5000
    for offset in range(0, total, batch_size):
        batch = collection.get(
            include=["documents", "metadatas"],
            limit=batch_size,
            offset=offset,
        )
        ids.extend(batch["ids"])
        documents.extend(batch["documents"])
        metadatas.extend(batch["metadatas"])
        if VERBOSE:
            print(f"  Loaded {len(ids):,}/{total:,} chunks for BM25 indexing...")

    # Tokenize all documents
    tokenized_corpus = [tokenize_for_bm25(doc) for doc in documents]

    # Build BM25 index
    bm25 = BM25Okapi(tokenized_corpus)

    # Save everything we need for search
    index_data = {
        "bm25": bm25,
        "ids": ids,
        "documents": documents,
        "metadatas": metadatas,
        "tokenized_corpus": tokenized_corpus,
    }

    index_path = Path(bm25_output_path) if bm25_output_path else BM25_INDEX_PATH / "bm25_index.pkl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "wb") as f:
        pickle.dump(index_data, f)

    if VERBOSE:
        print(f"  BM25 index built: {len(ids)} chunks indexed → {index_path}")


def load_bm25_index(index_path: str | Path | None = None) -> dict | None:
    """Load the BM25 index from disk. Returns None if not found.

    Args:
        index_path: Path to the BM25 pickle. Defaults to BM25_INDEX_PATH / "bm25_index.pkl".
    """
    path = Path(index_path) if index_path else BM25_INDEX_PATH / "bm25_index.pkl"
    if not path.exists():
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


# ===========================================================================
# ChromaDB Storage
# ===========================================================================

def store_chunks(chunks: list[dict], collection_name: str, embeddings: list[list[float]] | None = None):
    """Store chunks in a ChromaDB collection.
    
    If embeddings are provided, stores them. Otherwise stores documents only
    (used for parent chunks which don't need embeddings for search).
    """
    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [c["id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    # Add user-provided tags to metadata
    for meta in metadatas:
        # Ensure all metadata values are strings (ChromaDB requirement)
        for key, value in meta.items():
            if not isinstance(value, (str, int, float, bool)):
                meta[key] = str(value)

    # ChromaDB has a batch limit; process in groups of 500
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_docs = documents[i : i + batch_size]
        batch_metas = metadatas[i : i + batch_size]

        kwargs = {
            "ids": batch_ids,
            "documents": batch_docs,
            "metadatas": batch_metas,
        }

        if embeddings is not None:
            kwargs["embeddings"] = embeddings[i : i + batch_size]

        collection.upsert(**kwargs)


# ===========================================================================
# Main Ingestion Flow
# ===========================================================================

def ingest_document(
    filepath: str,
    collection: str = "reference",
    tags: str = "",
    child_collection_name: str | None = None,
    parent_collection_name: str | None = None,
    bm25_output_path: str | None = None,
):
    """Full ingestion pipeline for a single document.
    
    1. Load document text
    2. Create parent and child chunks
    3. Embed child chunks (parents don't need embeddings)
    4. Store both in ChromaDB
    5. Rebuild BM25 index
    """
    path = Path(filepath)
    if not path.exists():
        print(f"[!] File not found: {filepath}")
        sys.exit(1)

    filename = path.name
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    tag_string = ", ".join(tag_list)

    print(f"\n{'='*60}")
    print(f"INGESTING: {filename}")
    print(f"{'='*60}")

    # Step 1: Load
    print("\n[1/5] Loading document...")
    text = load_document(filepath)
    print(f"  Loaded {len(text):,} characters from {filename}")

    if len(text) < 50:
        print("[!] Document appears empty or too short. Skipping.")
        return

    # Step 2: Chunk (parent-child)
    print("\n[2/5] Creating parent-child chunks...")
    parent_chunks, child_chunks = create_parent_child_chunks(text, filename)
    print(f"  Created {len(parent_chunks)} parent chunks (avg {sum(len(p['text']) for p in parent_chunks) // max(len(parent_chunks), 1)} chars)")
    print(f"  Created {len(child_chunks)} child chunks (avg {sum(len(c['text']) for c in child_chunks) // max(len(child_chunks), 1)} chars)")

    # Add collection and tag metadata to all chunks
    for chunk in parent_chunks + child_chunks:
        chunk["metadata"]["collection_tag"] = collection
        chunk["metadata"]["tags"] = tag_string

    # Step 3: Embed child chunks only
    # Use embed_text (with contextual prefix) when available, fall back to raw text
    print("\n[3/5] Generating embeddings for child chunks...")
    child_texts = [c.get("embed_text", c["text"]) for c in child_chunks]
    child_embeddings = embed_texts(child_texts)
    print(f"  Generated {len(child_embeddings)} embeddings")

    # Step 4: Store in ChromaDB
    _parent_col = parent_collection_name or PARENT_COLLECTION
    _child_col = child_collection_name or CHILD_COLLECTION
    print("\n[4/5] Storing in ChromaDB...")
    store_chunks(parent_chunks, _parent_col, embeddings=None)
    print(f"  Stored {len(parent_chunks)} parent chunks in '{_parent_col}'")

    store_chunks(child_chunks, _child_col, embeddings=child_embeddings)
    print(f"  Stored {len(child_chunks)} child chunks in '{_child_col}'")

    # Step 5: Rebuild BM25 index
    print("\n[5/5] Rebuilding BM25 keyword index...")
    build_bm25_index(child_collection_name=_child_col, bm25_output_path=bm25_output_path)

    print(f"\n{'='*60}")
    print(f"DONE: {filename}")
    print(f"  Parents: {len(parent_chunks)} | Children: {len(child_chunks)}")
    print(f"  Collection: {collection} | Tags: {tag_string or '(none)'}")
    print(f"{'='*60}\n")


def show_status():
    """Display the current state of the knowledge base."""
    print(f"\n{'='*60}")
    print("KNOWLEDGE BASE STATUS")
    print(f"{'='*60}\n")

    # Check child collection
    try:
        child_col = chroma_client.get_collection(name=CHILD_COLLECTION)
        child_count = child_col.count()
        print(f"Child chunks (search index):  {child_count:,}")
    except Exception:
        child_count = 0
        print(f"Child chunks (search index):  0 (collection not created yet)")

    # Check parent collection
    try:
        parent_col = chroma_client.get_collection(name=PARENT_COLLECTION)
        parent_count = parent_col.count()
        print(f"Parent chunks (context):      {parent_count:,}")
    except Exception:
        parent_count = 0
        print(f"Parent chunks (context):      0 (collection not created yet)")

    # Check legacy collection
    try:
        legacy_col = chroma_client.get_collection(name="hydraulic-filter-kb")
        legacy_count = legacy_col.count()
        if legacy_count > 0:
            print(f"Legacy chunks (v1 format):    {legacy_count:,}  ← consider re-ingesting")
    except Exception:
        pass

    # Check BM25 index
    bm25_data = load_bm25_index()
    if bm25_data:
        print(f"BM25 keyword index:           {len(bm25_data['ids']):,} chunks indexed")
    else:
        print(f"BM25 keyword index:           not built yet")

    # List sources
    if child_count > 0:
        all_data = child_col.get(include=["metadatas"])
        sources = set()
        for meta in all_data["metadatas"]:
            sources.add(meta.get("source", "unknown"))
        print(f"\nIngested sources ({len(sources)}):")
        for src in sorted(sources):
            # Count chunks per source
            count = sum(1 for m in all_data["metadatas"] if m.get("source") == src)
            print(f"  • {src} ({count} child chunks)")

    print(f"\nVector store path: {VECTOR_STORE_PATH}")
    print(f"BM25 index path:   {BM25_INDEX_PATH}")
    print()


# ===========================================================================
# CLI
# ===========================================================================

def _resolve_vertical_config(platform_id: str | None, vertical_id: str | None):
    """Load vertical config if platform/vertical specified, else return None tuple."""
    if not platform_id or not vertical_id:
        return None, None, None
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from core.vertical_loader import get_vertical_config
        vc = get_vertical_config(platform_id, vertical_id)
        return vc.child_collection, vc.parent_collection, vc.bm25_index_path
    except Exception as e:
        print(f"[!] Could not load vertical config: {e}")
        print("    Falling back to default collection names.")
        return None, None, None


def main():
    parser = argparse.ArgumentParser(
        description="Fluidoracle — Document Ingestion Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Ingest into a specific vertical
  python -m core.retrieval.ingest --platform fps --vertical hydraulic_filtration doc.md

  # Ingest with default collection names (backward compatible)
  python -m core.retrieval.ingest doc.md --collection reference --tags "filtration"

  # Status and rebuild
  python -m core.retrieval.ingest --status
  python -m core.retrieval.ingest --rebuild-bm25 --platform fps --vertical hydraulic_filtration
        """,
    )
    parser.add_argument("filepath", nargs="?", help="Path to the document to ingest")
    parser.add_argument("--collection", default="reference", help="Collection tag (default: reference)")
    parser.add_argument("--tags", default="", help="Comma-separated tags for this document")
    parser.add_argument("--platform", default=None, help="Platform ID (e.g., fps, fds)")
    parser.add_argument("--vertical", default=None, help="Vertical ID (e.g., hydraulic_filtration)")
    parser.add_argument("--source-dir", default=None, help="Ingest all .md files from this directory")
    parser.add_argument("--status", action="store_true", help="Show knowledge base status")
    parser.add_argument("--rebuild-bm25", action="store_true", help="Rebuild the BM25 keyword index")

    args = parser.parse_args()

    # Resolve vertical-specific collection names
    child_col, parent_col, bm25_path = _resolve_vertical_config(args.platform, args.vertical)

    if args.status:
        show_status()
    elif args.rebuild_bm25:
        print("Rebuilding BM25 index...")
        build_bm25_index(
            child_collection_name=child_col or CHILD_COLLECTION,
            bm25_output_path=bm25_path,
        )
        print("Done.")
    elif args.source_dir:
        # Batch ingest all .md files from a directory
        source_dir = Path(args.source_dir)
        if not source_dir.exists():
            print(f"[!] Source directory not found: {source_dir}")
            sys.exit(1)
        md_files = sorted(source_dir.glob("*.md"))
        if not md_files:
            print(f"[!] No .md files found in {source_dir}")
            sys.exit(1)
        print(f"Found {len(md_files)} documents to ingest from {source_dir}")
        for f in md_files:
            ingest_document(
                str(f), args.collection, args.tags,
                child_collection_name=child_col,
                parent_collection_name=parent_col,
                bm25_output_path=bm25_path,
            )
        print(f"\nAll {len(md_files)} documents ingested.")
    elif args.filepath:
        ingest_document(
            args.filepath, args.collection, args.tags,
            child_collection_name=child_col,
            parent_collection_name=parent_col,
            bm25_output_path=bm25_path,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
