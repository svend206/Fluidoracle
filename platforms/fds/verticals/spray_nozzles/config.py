"""
Spray Nozzles — Vertical Configuration

All vertical-specific parameters for the spray nozzles vertical
within the Fluid Delivery Systems (FDS) platform.
"""
from __future__ import annotations

VERTICAL_ID = "spray_nozzles"
PLATFORM_ID = "fds"
DISPLAY_NAME = "Spray Nozzles"
SHORT_NAME = "nozzles"
DESCRIPTION = (
    "Expert AI consultation for industrial spray nozzle selection — "
    "atomization, droplet size engineering, coverage design, "
    "and application-specific nozzle recommendations."
)

# ChromaDB collection names
CHILD_COLLECTION = "spray_nozzles-children"
PARENT_COLLECTION = "spray_nozzles-parents"

# BM25 index path (relative to repo root vector-store/bm25/)
BM25_INDEX_FILENAME = "spray_nozzles.pkl"

# Retrieval tuning
CONFIDENCE_THRESHOLD_HIGH = 0.75
CONFIDENCE_THRESHOLD_MEDIUM = 0.40
RETRIEVAL_TOP_K = 10
SEMANTIC_WEIGHT = 0.60  # vs BM25 (0.40)

# Example questions for the landing page / UI
EXAMPLE_QUESTIONS = [
    "What nozzle gives a full cone pattern with ~200 µm SMD at 3 bar water pressure?",
    "How do I size nozzles for a spray dryer producing 500 kg/hr milk powder?",
    "I need to clean a 2m diameter tank with CIP — what nozzle type and placement?",
    "What's the best atomizer for SCR urea injection in a 400°C exhaust stream?",
]

# Warmup query (used at startup to pre-load models)
WARMUP_QUERY = "spray nozzle selection for industrial application"
