# Oracle Platform — Current State

**Date:** 2026-02-26
**Written by:** openclaw

---

## What This Project Is

Oracle is a platform for building domain-specific AI expert systems for industrial fluid component selection. Each vertical is a standalone expert: a curated knowledge base, a two-phase diagnostic consultation engine, and a web surface where engineers ask questions and get grounded, cited answers.

**Business model:** Free for engineers. Revenue from manufacturers via data exhaust, lead generation, and market intelligence. Closest analog: SpecialChem (specialchem.com, founded 2000). Oracle leapfrogs SpecialChem by adding the consultation layer and outcome tracking — it doesn't just answer questions, it learns from what actually happened after engineers followed its advice.

**Proof of concept:** TheSprayOracle.com is live. Erik built it. The spray nozzle vertical proved the architecture works. Everything here is applying that architecture at platform scale.

---

## Repository Map

| Repo | Purpose | State |
|------|---------|-------|
| `svend206/oracle` | Platform layer — pipeline engine, vertical template, docs | Active development |
| `svend206/filteroracle` | Hydraulic filter vertical — first platform vertical | Foundation complete, knowledge base empty |
| `svend206/sprayoracle` | Spray nozzle vertical — read only | Live at TheSprayOracle.com |

Local clones: `~/Projects/oracle`, `~/Projects/filteroracle`

---

## Layer Status

### Layer 1: Knowledge Collection (oracle-pipeline)

**What's built:**
- SQLite schema (`oracle.db`) — 8-layer data model, fully designed
- Bootstrap — seeds 7 fluids, 21 property records, 24 compatibility records, hydraulic-filters vertical (16 parameters, 8 outcome fields)
- CLI (`python -m pipeline bootstrap|status|run`)
- Base HTTP collector with retries, rate limiting, provenance tracking
- Brave Search API collector
- Phase 1 runner (standards search queries)
- Phase 2 content fetcher (raw URL fetch → markdown)
- Utility modules: hashing, logging, rate limiter

**What's been run:**
- Phase 1 and Phase 2 have executed against the hydraulic-filters vertical
- ~60 raw-fetch files, ~100 raw-research files produced
- ISO 16889:2022 and ISO 2941:2009 purchased and in possession (raw-fetch/)

**What's missing:**
- Synthesizer — raw content → Claude-structured chunks → SQLite (not built)
- Chroma integration — SQLite chunks → ChromaDB vector store (not built)
- LLM tagger — tags collected content against vertical ontology (not built)

**Verdict:** Collects but doesn't deliver. The pipeline produces raw material but the processing chain that converts it to usable knowledge doesn't exist yet.

---

### Layer 2: Knowledge Base (FilterOracle)

**What's built:**
- Full RAG pipeline: ChromaDB, BM25 hybrid search, cross-encoder reranker, verified query layer
- Scripts: ingest.py, batch_ingest.py, hybrid_search.py, verified_query.py, test_setup.py, test_coverage.py
- 12 curated reference documents in `ai/02-knowledge-base/curated-references/` — well-structured markdown, covering the core curriculum
- Corrections pipeline and gap tracker
- SOURCING-BACKLOG.md — claim-by-claim sourcing status documented

**What's missing:**
- **Nothing has been ingested.** ChromaDB is empty. The vector store does not exist.
- No test cases written.
- No coverage baseline established.

**Verdict:** All the infrastructure to run a knowledge base exists. The knowledge base itself is empty.

---

### Layer 3: Consulting Surface (FilterOracle)

**What's built:**
- Full FastAPI backend — main.py, consultation_engine.py, answer_engine.py, invention_engine.py, database.py, training.py, email_utils.py
- Two-phase consultation flow (gathering → answering) — fully implemented
- React + Vite + Tailwind frontend — Ask, Browse, Consult, Invent pages
- Docker + Caddy deployment stack
- Outcome tracking schema (sessions, follow-ups) — in DB schema
- Passwordless email auth — implemented
- Training data logger — implemented

**What's missing:**
- Has never been run end-to-end with a real knowledge base
- No .env configured locally
- Frontend example questions are SprayOracle placeholders
- No test cases to validate consultation quality
- Not deployed

**Verdict:** Functionally complete. Untested. Cannot deliver value until the knowledge base is populated.

---

## The Single Biggest Gap

The knowledge base is empty. Every other component is ready. The backend can run, the consultation engine is built, the frontend exists, the curated references are written. But if you asked FilterOracle a question today, it would answer from the system prompt alone — no retrieval, no citations, no confidence scores.

Ingesting the 12 curated reference documents takes one command and about 10 minutes. That single action transforms FilterOracle from "infrastructure" to "working product."

---

## Sprint Plan

### Sprint 2 — First Working Oracle
*Transforms the system from infrastructure to product.*

**Ingest & Verify:**
- [x] Ingest `ai/02-knowledge-base/curated-references/` into ChromaDB (179 parents, 467 children)
- [x] Run `test_setup.py` — 16/16 passing
- [x] Configure local `.env` — OpenAI + Anthropic keys configured
- [x] Smoke test `/ask` and `/consult` — both working (HIGH confidence, 12 sources cited, gathering phase operational)
- [x] Write 10 test cases with known correct answers in `ai/06-test-cases/` — **10/10 passing**

**Retrieval improvements (from CHUNKING-AND-RETRIEVAL-AUDIT.md Tier 2):**
- [x] Metadata filtering — `search()` accepts `metadata_filter` dict, passed to ChromaDB `where` + BM25 post-filter
- [x] Query-adaptive BM25 weighting — spec queries (ISO codes, part numbers) auto-boost BM25 to 0.75
- [x] RRF score fusion — replaced linear combination with reciprocal rank fusion (k=60)

**Fluid database (from FLUID-DATABASE-DESIGN.md Steps 1-2):**
- [x] Schema migration — added `fluid_class`, `viscosity_grade`, `trade_names`, `base_stock` to `fluids`
- [x] Created `fluid_static_properties` table (pour point, flash point, VI — 16 records)
- [x] Created `fluid_viscosity_models` table (Walther coefficients — 3 mineral oil grades)
- [x] Enriched all fluids with new fields (ISO classes, trade names, base stock from TDS)
- [x] Added diesel fuel record (3 temperature points, pour/flash point)

**Wrap up:**
- [x] Update `oracle-pipeline/SESSION_HANDOFF.md`

### Sprint 3 — Fill the Knowledge Base
*Go from 12 documents to full curriculum coverage.*

- [ ] Build oracle-pipeline synthesizer (raw content → Claude-structured chunks)
- [ ] Build Chroma integration (pipeline output → ChromaDB ingest)
- [ ] Synthesize curated references from ISO 16889:2022 and ISO 2941:2009
- [ ] Work through `SOURCING-BACKLOG.md` — ground every claim in a possessed source
- [ ] Execute `MANUAL_ACQUISITION.md` — send manufacturer emails
- [ ] Run `test_coverage.py` after each ingest wave; target all 9 curriculum phases

### Sprint 4 — Calculation Tools
*FilterOracle can do math, not just retrieve text.*

- [ ] Pressure drop calculator (ΔP from rated ΔP, viscosity ratio, flow ratio)
- [ ] Beta ratio selector (target + baseline ISO code → required β rating)
- [ ] ISO code converter (ISO 4406 ↔ NAS 1638 ↔ SAE AS4059)
- [ ] Kidney loop sizer (target cleanliness, reservoir volume, ingression rate → flow rate)
- [ ] Cold-start bypass risk calculator (cold viscosity, collapse pressure → risk flag)

### Sprint 5 — Launch
*FilterOracle is live.*

- [ ] Deploy to a server (Docker + Caddy + Cloudflare)
- [ ] Update frontend example questions for hydraulic filter domain
- [ ] Soft launch — share with a small group of hydraulic engineers
- [ ] Validate consultation quality against real engineer questions

### Sprint 6 — CPVP and Outcome Tracking
*Close the loop between recommendation and reality.*

- [ ] Implement commissioning module schema additions
- [ ] Auto-generate three-document CPVP set from completed consultations
- [ ] Follow-up cron at 30/90/180 days post-recommendation
- [ ] Publish CPVP white paper to Hydraulic Institute — establish the standard before adoption

### Horizon — Second Vertical
*PumpOracle or the next vertical with organic demand.*

Watch what adjacent questions appear in FilterOracle consultations. The second vertical should follow user pull, not strategic planning.

---

## Open Design Questions

1. **CPVP publication timing** — Publish the white paper before or after launch? Before is riskier but establishes priority. After is safer but loses the first-mover narrative.
2. **Consultation sharing / library** — Add `is_public`, `is_anonymized` to the consultations table. Shared consultations = the "completed builds" of PCPartPicker. Solves cold-start.
3. **SEO content artifacts** — The pipeline produces a second output: publication-ready selection guides and application notes. The schema additions for this (`content_artifacts` table) are designed but not implemented.
4. **Forum presence strategy** — Eng-Tips (Hydraulic & Pneumatic Engineering) and Reddit (r/hydraulics). Accounts need to be created, profile statements written. Active participation only after Phase 4 identifies specific knowledge gaps.
