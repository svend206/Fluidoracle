# SESSION_HANDOFF.md — Oracle Pipeline

**Last updated:** 2026-02-26 (Sprint 2 complete)

## Current State

**Sprint 2 is COMPLETE.** FilterOracle has a working knowledge base, retrieval pipeline, and consulting surface.

### What Exists

**oracle-pipeline (this repo):**
- `oracle.db` schema v3: fluids (8), static properties (16), viscosity models (3), manufacturers (8), hydraulic-filter vertical with 16 parameters
- Bootstrap seeds all reference data. Run `python3 -m pipeline bootstrap` to rebuild from scratch.

**FilterOracle (`svend206/FilterOracle`):**
- 12 curated reference documents ingested into ChromaDB (179 parents, 467 children)
- Markdown-aware chunking (splits at `##`/`###` headers)
- Contextual embedding prefixes (`Document: {source} | Section: {header}`)
- Hybrid search: semantic + BM25 with RRF fusion and query-adaptive weighting
- Cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`)
- DB-backed vendor detection (reads manufacturers from oracle.db)
- FastAPI backend: `/api/ask` and `/api/consult/sessions` both operational
- 10/10 retrieval test cases passing
- 3 Parker source PDFs in `source-files/parker/` (not yet ingested — raw PDFs need extraction)

### Python 3.9 Compatibility

The MacBook runs Python 3.9. All files have `from __future__ import annotations`. Pydantic requires `eval_type_backport` package. Do not use `X | Y` in runtime contexts (only in type annotations).

### What's Next (Sprint 3)

1. **Build synthesizer** — Extract and synthesize content from raw PDFs (Parker HTM-5, ISO standards in `raw-fetch/`) into curated reference markdown
2. **Ingest Parker source docs** — The 3 PDFs in `source-files/parker/` need text extraction → chunking → ingestion
3. **Expand knowledge base** — Work through SOURCING-BACKLOG.md, execute MANUAL_ACQUISITION.md
4. **Eaton documents** — Erik has ~30 Eaton PDFs + zip files in Downloads. Major source material.
5. **CPVP design** — Commissioning module (designed in MEMORY.md, not implemented)

### Files That Matter

| File | What It Does |
|---|---|
| `platform-docs/STATUS.md` | Sprint checklist — source of truth for what's done |
| `platform-docs/CHUNKING-AND-RETRIEVAL-AUDIT.md` | Pre-ingest analysis and improvement recommendations |
| `platform-docs/FLUID-DATABASE-DESIGN.md` | Fluid schema design with sourcing strategy |
| `platform-docs/SPRAYORACLE-RECOMMENDATIONS.md` | Read-only audit of SprayOracle with improvement recs |
| `oracle-pipeline/pipeline/db.py` | Schema DDL — all tables defined here |
| `oracle-pipeline/pipeline/bootstrap.py` | Seed data — fluids, manufacturers, vertical params |

### Credentials

`.env` files are gitignored. They contain OpenAI + Anthropic API keys. Located at `~/Projects/filteroracle/.env`. Copy from `~/Downloads/.env` (SprayOracle's) if missing.

### Don't Forget

- **Every knowledge base claim must trace to a document in the repo.** No inventing facts.
- **Sub-agent rules in TOOLS.md are hard limits.** No parallel web research agents.
- **Vendor patterns live in oracle.db**, not in Python. New vertical = new manufacturer seeds in bootstrap.
