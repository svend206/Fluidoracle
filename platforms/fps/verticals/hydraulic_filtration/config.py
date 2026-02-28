"""
Hydraulic Filtration — Vertical Configuration

All vertical-specific parameters for the hydraulic filtration vertical
within the Fluid Power Systems (FPS) platform.
"""
from __future__ import annotations

VERTICAL_ID = "hydraulic_filtration"
PLATFORM_ID = "fps"
DISPLAY_NAME = "Hydraulic Filtration"
SHORT_NAME = "filtration"
DESCRIPTION = (
    "Expert AI consultation for hydraulic and lubrication system filtration — "
    "filter selection, contamination control, ISO cleanliness targeting, "
    "pressure drop analysis, and cold-start sizing."
)

# ChromaDB collection names
CHILD_COLLECTION = "hydraulic_filtration-children"
PARENT_COLLECTION = "hydraulic_filtration-parents"

# BM25 index path (relative to repo root vector-store/bm25/)
BM25_INDEX_FILENAME = "hydraulic_filtration.pkl"

# Retrieval tuning
CONFIDENCE_THRESHOLD_HIGH = 0.75
CONFIDENCE_THRESHOLD_MEDIUM = 0.40
RETRIEVAL_TOP_K = 10
SEMANTIC_WEIGHT = 0.60  # vs BM25 (0.40)

# Example questions for the landing page / UI
EXAMPLE_QUESTIONS = [
    "How do I select a return line filter for a 120 L/min system targeting ISO 16/14/11?",
    "What beta ratio do I need for servo valve protection?",
    "My excavator's hydraulic oil is consistently dirty — how do I diagnose the contamination source?",
    "How do I calculate pressure drop across a filter at cold-start viscosity?",
]

# Warmup query (used at startup to pre-load models)
WARMUP_QUERY = "hydraulic filter selection for industrial system"
