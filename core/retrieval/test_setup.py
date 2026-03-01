"""
Fluidoracle — Setup Verification (v2: Hybrid Pipeline)
==============================================================
Tests all components of the hybrid retrieval pipeline:
  1. Python packages
  2. API key configuration
  3. ChromaDB read/write
  4. OpenAI Embeddings
  5. BM25 keyword index
  6. Cross-encoder reranker
  7. End-to-end hybrid search

Run: py -3.12 test_setup.py
"""

import sys
import traceback

# Try importing rich for pretty output; fall back to plain text
try:
    from rich.console import Console
    console = Console()
    def ok(msg): console.print(f"  [green]✓[/green] {msg}")
    def fail(msg): console.print(f"  [red]✗[/red] {msg}")
    def section(msg): console.print(f"\n[bold]{msg}[/bold]")
except ImportError:
    def ok(msg): print(f"  ✓ {msg}")
    def fail(msg): print(f"  ✗ {msg}")
    def section(msg): print(f"\n{msg}")

passed = 0
failed = 0

def check(name, fn):
    global passed, failed
    try:
        fn()
        ok(name)
        passed += 1
    except Exception as e:
        fail(f"{name}: {e}")
        failed += 1


# ===========================================================================
# 1. Python Packages
# ===========================================================================
section("1. Python packages")

for pkg in ["chromadb", "openai", "pypdf", "dotenv", "rich", "rank_bm25", "sentence_transformers", "numpy"]:
    def _check(p=pkg):
        # Map package names to import names
        import_map = {"dotenv": "dotenv", "sentence_transformers": "sentence_transformers"}
        __import__(import_map.get(p, p))
    check(pkg, _check)


# ===========================================================================
# 2. Configuration
# ===========================================================================
section("2. Configuration")

def check_api_key():
    from config import OPENAI_API_KEY
    assert OPENAI_API_KEY and OPENAI_API_KEY != "sk-your-key-here", "API key not set in .env"
check("API key configured", check_api_key)

def check_embedding_model():
    from config import EMBEDDING_MODEL
    assert EMBEDDING_MODEL, "Embedding model not configured"
    ok(f"  Embedding model: {EMBEDDING_MODEL}")
    passed  # already counted by check()
check("Embedding model set", check_embedding_model)

def check_paths():
    from config import VECTOR_STORE_PATH, BM25_INDEX_PATH
    assert VECTOR_STORE_PATH.exists(), f"Vector store path missing: {VECTOR_STORE_PATH}"
    assert BM25_INDEX_PATH.exists(), f"BM25 index path missing: {BM25_INDEX_PATH}"
check("Storage paths exist", check_paths)


# ===========================================================================
# 3. ChromaDB
# ===========================================================================
section("3. ChromaDB")

def check_chromadb_rw():
    import chromadb
    from config import VECTOR_STORE_PATH
    client = chromadb.PersistentClient(path=str(VECTOR_STORE_PATH))
    # Create temp collection, write, read, delete
    col = client.get_or_create_collection(name="setup-test-temp")
    col.upsert(ids=["test-1"], documents=["hydraulic filter test document"])
    result = col.query(query_texts=["hydraulic filter"], n_results=1)
    assert result["ids"][0][0] == "test-1", "Read-back failed"
    client.delete_collection(name="setup-test-temp")
check("ChromaDB read/write", check_chromadb_rw)


# ===========================================================================
# 4. OpenAI Embeddings
# ===========================================================================
section("4. OpenAI Embeddings")

def check_embeddings():
    from openai import OpenAI
    from config import OPENAI_API_KEY, EMBEDDING_MODEL
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=["test hydraulic filter embedding"])
    assert len(resp.data[0].embedding) > 0, "Empty embedding returned"
check(f"Generate embedding", check_embeddings)


# ===========================================================================
# 5. BM25 Keyword Search
# ===========================================================================
section("5. BM25 keyword search")

def check_bm25():
    from rank_bm25 import BM25Okapi
    corpus = [
        ["spray", "nozzle", "flow", "rate"],
        ["hollow", "cone", "pattern", "droplet"],
        ["flat", "fan", "coverage", "angle"],
    ]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(["nozzle", "flow"])
    assert scores[0] > scores[1], "BM25 scoring not working as expected"
check("BM25 index and search", check_bm25)


# ===========================================================================
# 6. Cross-Encoder Reranker
# ===========================================================================
section("6. Cross-encoder reranker")

def check_cross_encoder():
    from sentence_transformers import CrossEncoder
    from config import CROSS_ENCODER_MODEL
    model = CrossEncoder(CROSS_ENCODER_MODEL)
    scores = model.predict([
        ("What is the flow rate of a hydraulic filter?", "The flow rate depends on pressure and orifice diameter."),
        ("What is the flow rate of a hydraulic filter?", "The weather today is sunny and warm."),
    ])
    assert scores[0] > scores[1], "Cross-encoder not ranking relevant content higher"
check(f"Cross-encoder reranking", check_cross_encoder)


# ===========================================================================
# 7. End-to-End Hybrid Search
# ===========================================================================
section("7. End-to-end hybrid search")

def check_e2e():
    import chromadb
    import pickle
    import numpy as np
    from rank_bm25 import BM25Okapi
    from openai import OpenAI
    from config import (
        OPENAI_API_KEY, EMBEDDING_MODEL, VECTOR_STORE_PATH,
        BM25_INDEX_PATH, CHILD_COLLECTION, PARENT_COLLECTION,
    )

    client = chromadb.PersistentClient(path=str(VECTOR_STORE_PATH))
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    # Create temp collections
    child_temp = "e2e-test-children"
    parent_temp = "e2e-test-parents"

    try:
        child_col = client.get_or_create_collection(name=child_temp, metadata={"hnsw:space": "cosine"})
        parent_col = client.get_or_create_collection(name=parent_temp)

        # Insert test data
        test_docs = [
            {
                "parent_text": "Hollow cone nozzles produce a ring-shaped spray pattern. They are commonly used in gas cooling and FGD applications. The droplet size is typically 100-500 microns depending on pressure and orifice size.",
                "child_text": "Hollow cone nozzles produce a ring-shaped spray pattern with droplet sizes of 100-500 microns.",
                "source": "test-reference.pdf",
            },
            {
                "parent_text": "Full cone nozzles produce a solid circular spray pattern with uniform distribution. They are used in washing, cooling, and chemical processing. Flow rates range from 0.1 to 500 GPM.",
                "child_text": "Full cone nozzles produce solid circular patterns used in washing and cooling applications.",
                "source": "test-reference.pdf",
            },
            {
                "parent_text": "The model 1/4GG-SS2.8 is a full cone nozzle made of 316 stainless steel. At 40 PSI it delivers 2.8 GPM with a 65 degree spray angle.",
                "child_text": "1/4GG-SS2.8 full cone nozzle, 316SS, 2.8 GPM at 40 PSI, 65 degree angle.",
                "source": "test-catalog.pdf",
            },
        ]

        # Embed and store children
        child_texts = [d["child_text"] for d in test_docs]
        resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=child_texts)
        embeddings = [item.embedding for item in resp.data]

        child_ids = [f"e2e-child-{i}" for i in range(len(test_docs))]
        parent_ids = [f"e2e-parent-{i}" for i in range(len(test_docs))]

        child_col.upsert(
            ids=child_ids,
            documents=child_texts,
            embeddings=embeddings,
            metadatas=[{"source": d["source"], "parent_id": pid} for d, pid in zip(test_docs, parent_ids)],
        )

        parent_col.upsert(
            ids=parent_ids,
            documents=[d["parent_text"] for d in test_docs],
            metadatas=[{"source": d["source"]} for d in test_docs],
        )

        # Test semantic search
        query_resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=["hollow cone spray pattern"])
        query_emb = query_resp.data[0].embedding
        sem_results = child_col.query(query_embeddings=[query_emb], n_results=2)
        assert "e2e-child-0" in sem_results["ids"][0], "Semantic search didn't find hollow cone doc"

        # Test BM25 search
        tokenized = [doc.lower().split() for doc in child_texts]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores("1/4gg-ss2.8".split())
        best_idx = int(np.argmax(scores))
        assert best_idx == 2, "BM25 didn't find catalog model number"

        # Test parent resolution
        parent_result = parent_col.get(ids=["e2e-parent-2"])
        assert "40 PSI" in parent_result["documents"][0], "Parent resolution failed"

        ok("  Semantic → BM25 → Parent resolution: all working")

    finally:
        # Cleanup
        try:
            client.delete_collection(name=child_temp)
        except Exception:
            pass
        try:
            client.delete_collection(name=parent_temp)
        except Exception:
            pass

check("End-to-end hybrid pipeline", check_e2e)


# ===========================================================================
# Summary
# ===========================================================================
section(f"\n{'='*50}")
if failed == 0:
    section(f"All checks passed! ✓ ({passed}/{passed + failed})")
    print("\nYour hybrid retrieval pipeline is ready.")
    print("Next steps:")
    print("  1. Ingest a document:  py -3.12 ingest.py path/to/document.pdf")
    print("  2. Test a query:       py -3.12 query.py \"your question here\"")
    print("  3. Verified query:     py -3.12 verified_query.py \"your question\"")
else:
    section(f"Some checks failed ({failed} of {passed + failed}). See above for details.")

sys.exit(0 if failed == 0 else 1)
