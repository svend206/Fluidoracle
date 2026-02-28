from __future__ import annotations
"""
Fluidoracle — Retrieval Configuration
=======================================
Shared retrieval parameters for all verticals.
Vertical-specific values (collection names, BM25 paths) come from
vertical config — see core.vertical_loader.

This module provides shared defaults and paths.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent.parent  # core/retrieval/config.py → core → repo root
VECTOR_STORE_PATH = PROJECT_ROOT / "vector-store"
BM25_INDEX_PATH = PROJECT_ROOT / "vector-store" / "bm25"
TRAINING_DATA_DIR = PROJECT_ROOT / "ai" / "08-training-data"
CORRECTIONS_DIR = PROJECT_ROOT / "ai" / "corrections"
GAP_TRACKER_PATH = PROJECT_ROOT / "ai" / "gap-tracker.jsonl"

# Ensure critical directories exist
VECTOR_STORE_PATH.mkdir(parents=True, exist_ok=True)
BM25_INDEX_PATH.mkdir(parents=True, exist_ok=True)
TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Environment / API Keys
# ---------------------------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# Embedding Settings (shared across all verticals)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536  # dimensions for text-embedding-3-small

# ---------------------------------------------------------------------------
# ChromaDB Collection Names — DEFAULTS
# These are overridden per-vertical via vertical config.
# Kept here for backward compatibility and standalone usage.
# ---------------------------------------------------------------------------
CHILD_COLLECTION = "hydraulic_filtration-children"
PARENT_COLLECTION = "hydraulic_filtration-parents"
LEGACY_COLLECTION = "hydraulic-filter-kb"

# ---------------------------------------------------------------------------
# Chunking Parameters (Parent-Child) — shared across verticals
# ---------------------------------------------------------------------------
PARENT_CHUNK_SIZE = 2000       # characters
PARENT_CHUNK_OVERLAP = 200     # characters
CHILD_CHUNK_SIZE = 400         # characters
CHILD_CHUNK_OVERLAP = 50       # characters

# ---------------------------------------------------------------------------
# Hybrid Search Parameters — shared defaults (verticals can override)
# ---------------------------------------------------------------------------
SEMANTIC_WEIGHT = 0.60
BM25_WEIGHT = 0.40
SEMANTIC_TOP_K = 30
BM25_TOP_K = 30
RERANK_CANDIDATES = 20
FINAL_TOP_K = 10

# ---------------------------------------------------------------------------
# Cross-Encoder Reranker (local, no API cost)
# ---------------------------------------------------------------------------
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ---------------------------------------------------------------------------
# Confidence Thresholds (for verified_query)
# ---------------------------------------------------------------------------
HIGH_CONFIDENCE_THRESHOLD = 0.75
MEDIUM_CONFIDENCE_THRESHOLD = 0.40

# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
VERBOSE = True
