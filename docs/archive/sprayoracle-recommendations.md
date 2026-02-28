# SprayOracle — Improvement Recommendations

**Date:** 2026-02-26
**Author:** openclaw (read-only audit of `svend206/sprayoracle`)
**Context:** Lessons learned from the FilterOracle chunking/retrieval audit and platform architecture work. These recommendations apply the same analysis to SprayOracle's codebase.

**Important:** SprayOracle is read-only for me. This document is a recommendation list, not a change log. Erik (or whoever works on SprayOracle) decides what gets implemented and when.

---

## 1. Chunking — Same Problems, Same Fixes

SprayOracle's `ingest.py` is the original codebase that FilterOracle was forked from. It has the same character-based chunking with no structural awareness.

### 1.1 Add Markdown-Aware Chunking

SprayOracle's knowledge base includes `spray-nozzle-research-reference.md` and whatever curated references exist or will be created. These are structured markdown documents. The chunker splits them by character count, breaking sections mid-topic.

**Recommendation:** Port the markdown-aware chunking from FilterOracle's updated `ingest.py`. Split `.md` files at `##`/`###` header boundaries. Each section becomes a parent chunk (capped at 4000 chars). This is a direct code transplant — the implementation already exists and is tested.

### 1.2 Add Contextual Embedding Prefixes

Child chunks are embedded in isolation. A chunk saying "typical Cd values range from 0.3 to 0.45" has no embedding context for what component or nozzle type it refers to.

**Recommendation:** Port the contextual prefix system from FilterOracle. Before embedding each child chunk, prepend `Document: {filename} | Section: {header} | `. Store the prefix in metadata, use it only for embedding generation, keep raw text for display.

### 1.3 Re-Ingest After Changes

Both changes above affect embeddings. The existing knowledge base (if populated) would need a full re-ingest after applying them. Since `source-files/` is currently empty (only `.gitkeep`), this is a non-issue if applied before the first real ingest.

---

## 2. Vendor Patterns — Move to Database

SprayOracle has the original hardcoded vendor patterns in `verified_query.py`:
- Spraying Systems Co., Lechler, BETE, PNR-Italia, Delavan, Danfoss, Schlick, GEA/Niro

These are correct for the spray nozzle domain. The problem isn't accuracy — it's architecture. When SprayOracle connects to the Oracle platform (which it should eventually), vendor identity should come from the shared `manufacturers` table in `oracle.db`, not from Python dicts.

**Recommendation:** When SprayOracle joins the platform, port the DB-backed vendor detection from FilterOracle's updated `verified_query.py`. In the meantime, the hardcoded patterns work fine — this is a scaling concern, not a bug.

**Also:** Register spray nozzle manufacturers in the platform's `bootstrap.py` so they exist in `oracle.db` alongside the hydraulic filter manufacturers. The manufacturer registry should be platform-wide.

---

## 3. System Prompt — Massive and Monolithic

The system prompt in `backend/answer_engine.py` is ~4,000 tokens of inline text. It contains:
- Core reference data (dimensionless numbers, SMD correlations, fluid properties, drop breakup regimes)
- Detailed behavioral instructions (citation discipline, assumption hygiene, feasibility checks)
- Vendor neutrality rules
- Correlation usage rigor requirements

This is impressive in depth but creates several problems:
1. **Every API call pays for ~4K tokens of system prompt** whether or not the question needs correlations or fluid property data.
2. **The reference data is not versioned or auditable.** Correlations embedded in a Python string can't be traced to a source document. If the Lefebvre correlation has a typo, finding and fixing it requires editing Python code.
3. **The behavioral instructions are not reusable.** FilterOracle will need similar citation discipline and assumption hygiene rules. Copy-pasting system prompt blocks between verticals is the same anti-pattern as hardcoded vendor patterns.

### Recommendations:

**3.1 — Extract reference data to the knowledge base.** The SMD correlations, dimensionless number definitions, fluid properties, and drop breakup regimes should be curated reference documents in the knowledge base, not inline system prompt text. They would then be retrieved when relevant (via the RAG pipeline) instead of sent on every call. This cuts system prompt cost and makes the data auditable.

**3.2 — Split behavioral instructions into a platform-level prompt template.** Citation discipline, assumption hygiene, and feasibility check requirements are domain-general — they apply to any Oracle vertical. Extract them into a shared prompt template that each vertical inherits. Vertical-specific instructions (spray nozzle types, manufacturer lists) stay in the vertical's config.

**3.3 — Version the system prompt.** Store the system prompt (or its components) as files in the repo, not as Python string literals. This enables diff tracking, review, and A/B testing.

---

## 4. Backend Bugs and Hardening

From the `VERIFICATION_AND_OUTCOMES_REPORT.md` (which is an excellent self-audit):

### 4.1 Empty `refined_query` Bug

If Claude emits `<refined_query></refined_query>` (empty), the system runs RAG on an empty string. This produces garbage results.

**Fix:** Validate `refined_query` is non-empty before retrieval. Fall back to constructing a query from the conversation history (extract key terms from user messages).

### 4.2 Hard Gathering Timeout

The 6-turn nudge (`MAX_GATHERING_TURNS = 6`) is a soft mechanism. There's no hard cutoff — if Claude ignores the nudge, the session stays in gathering indefinitely.

**Fix:** Add a hard transition at turn 10 (or configurable). Auto-construct a retrieval query from the conversation and force transition to answering phase.

### 4.3 Truncated Signal Tag

If `max_tokens` truncates Claude's response mid-`<consultation_signal>` tag, the opening tag without a closing tag will be visible to the user as raw XML.

**Fix:** Add a fallback regex that catches orphaned opening tags and strips them.

---

## 5. Knowledge Base — Empty

The most significant finding: `source-files/` contains only `.gitkeep`. There are no curated reference documents in the repo (unlike FilterOracle which has 12). The knowledge base infrastructure is fully built — ingestion, hybrid search, reranking, verification, table enhancement — but there's nothing in it.

The system prompt's CORE REFERENCE DATA section compensates by embedding correlations and property data directly, but this means:
- Every answer comes from the system prompt (domain knowledge) or hallucination
- The RAG pipeline is never exercised
- The verification system (confidence scoring, source diversity, gap tracking) produces no value
- The training data logger captures no retrieval-grounded examples

### Recommendation:

**5.1 — Create curated reference documents.** The same pattern used for FilterOracle:
- `REFERENCE-Atomization-Fundamentals.md` (breakup regimes, Weber/Ohnesorge, primary atomization)
- `REFERENCE-SMD-Correlations.md` (Lefebvre, Radcliffe, Jasuja, Nukiyama-Tanasawa — with validity ranges and source citations)
- `REFERENCE-Pressure-Swirl-Nozzles.md` (design, flow number, spray angle, capacity)
- `REFERENCE-Airblast-Atomizers.md` (prefilming vs plain-jet, ALR effects)
- `REFERENCE-Fluid-Properties.md` (water, diesel, kerosene, heavy fuel, slurries — with temperature dependence)
- `REFERENCE-Application-Selection-Guide.md` (application → nozzle type mapping)
- etc.

Each reference must trace every claim to a source document in the repo. The correlations currently in the system prompt would move here — with proper citations.

**5.2 — Move CORE REFERENCE DATA out of the system prompt.** Once curated references exist and are ingested, the system prompt shrinks to behavioral instructions only. Correlations and property data come through retrieval, with proper citations and confidence scores.

---

## 6. Platform Convergence

SprayOracle and FilterOracle share ~80% of their code. The divergence will get worse over time as improvements are made independently. The platform architecture was designed to prevent this.

### Current State:
| Component | SprayOracle | FilterOracle | Should Be |
|---|---|---|---|
| `ingest.py` | Original (character-based) | Updated (markdown-aware + contextual prefixes) | Platform shared |
| `hybrid_search.py` | Original | Original (identical) | Platform shared |
| `verified_query.py` | Hardcoded spray vendors | DB-backed vendor detection | Platform shared |
| `enhance_tables.py` | Hardcoded spray catalog map | DB-backed via `verified_query` | Platform shared |
| `config.py` | Spray collection names | Filter collection names | Vertical config only |
| `batch_ingest.py` | Original | Updated (uses `embed_text`) | Platform shared |
| Backend | Spray-specific system prompts | Filter-specific system prompts | Vertical config over shared engine |

### Recommendation:

**6.1 — Extract the shared retrieval engine into the platform repo.** `ingest.py`, `hybrid_search.py`, `verified_query.py`, `enhance_tables.py`, `batch_ingest.py` should live in `oracle/` (the platform repo) as a shared package. Each vertical imports them and provides its own `config.py` (collection names, thresholds) and database connection.

**6.2 — Don't do this yet.** The platform extraction is Sprint 6+ work. For now, the pragmatic path is: when FilterOracle's retrieval code is validated through Sprint 2, manually port the improvements back to SprayOracle. Track the delta so the eventual extraction is clean.

---

## 7. Summary — Priority Order

| # | Recommendation | Effort | Impact | When |
|---|---|---|---|---|
| 1 | Create curated reference documents + ingest | Days | **Critical** — KB is empty | First |
| 2 | Move CORE REFERENCE DATA from system prompt to KB | Hours | High — cost savings + auditability | After #1 |
| 3 | Port markdown-aware chunking + contextual prefixes | 1 hour (code transplant) | High — better chunk quality | Before #1 |
| 4 | Fix empty `refined_query` bug | 30 min | Medium — prevents garbage retrieval | Anytime |
| 5 | Add hard gathering timeout | 30 min | Medium — prevents stuck sessions | Anytime |
| 6 | Extract behavioral prompt into platform template | 2-3 hours | Medium — reusability across verticals | Sprint 3+ |
| 7 | Register spray manufacturers in oracle.db | 30 min | Low (currently works fine hardcoded) | When platform connects |
| 8 | Extract shared retrieval engine to platform | Days | Architectural — prevents drift | Sprint 6+ |
