"""Quick test to verify table index children improve search results."""
import sys
import os
import warnings
import logging

os.environ["TQDM_DISABLE"] = "1"
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

sys.path.insert(0, os.path.dirname(__file__))

# Suppress verbose output from hybrid_search
from . import config
config.VERBOSE = False

from .hybrid_search import search

queries = [
    "tungsten carbide tip flow rate at 150 bar",
    "spray drying nozzle capacity data",
    "descaling nozzle flow rate performance data",
    "quick connect nozzle flow rate at 40 psi",
    "FullJet nozzle spray angle performance",
]

for q in queries:
    results = search(q, top_k=5)
    print(f"\n=== {q} ===")
    for r in results[:5]:
        meta = r.get("metadata", {})
        idx = "IDX" if meta.get("is_table_index") else "   "
        # Handle different possible key names for the reranker score
        score = r.get("reranker_score", r.get("rerank_score", r.get("score", 0.0)))
        src = r.get("source", "unknown")
        child = r.get("child_text", "")[:100].replace("\n", " ")
        print(f"  [{idx}] {score:.3f} | {src}")
        print(f"         {child}")
    print()
