# Session Handoff — 2026-02-24

This document was written at the end of a long session to preserve context for the next session.
Read this before doing anything else in this project.

---

## What This Project Is

Erik Cullen is building a platform of domain-specific AI expert systems ("Oracles") for industrial
fluid component selection and diagnostics. The first working Oracle already exists at
**TheSprayOracle.com** (spray nozzle vertical) — Erik built it. We are NOT building the Oracle
interface. We are building the **knowledge pipeline** that populates the knowledge base that
feeds the Oracle, and designing the **data schema** that the Oracle platform will use.

The plan is to apply the Spray Oracle's structure to other verticals: hydraulic filters (first),
pumps, valves, gaskets, nozzles, etc. — at least a dozen verticals total.

**Business model:** Free for engineers (no password — email + code auth, already implemented).
Revenue from manufacturers via data exhaust, lead generation, and market intelligence.
Closest analog: SpecialChem (founded 2000, Paris). Platform leapfrogs SpecialChem by adding
the consultation layer and outcome tracking.

---

## Repository Structure

All pipeline code lives at:
`/Users/oracle/.openclaw/workspace/oracle-pipeline/`

Erik will share the Spray Oracle repo (the Oracle interface / consulting surface) when he's back
at a computer. At that point, read its structure before touching anything.

### Key files already written:
- `ARCHITECTURE.md` — Full system architecture (v0.1, updated with forum lifecycle)
- `SCHEMA.md` — Revised schema design (v0.2) — the authoritative data model
- `pipeline/db.py` — Unified SQLite schema (oracle.db), all 8 layers
- `pipeline/bootstrap.py` — Seeds fluids, fluid properties, compatibility, hydraulic-filters vertical
- `pipeline/cli.py` — CLI: `python -m pipeline bootstrap/status/run`
- `pipeline/collectors/base.py` — Base HTTP collector (retries, rate limiting, provenance)
- `pipeline/collectors/brave_search.py` — Brave Search API wrapper
- `pipeline/phases/phase1_standards.py` — Phase 1 runner (partial — Brave queries only)
- `pipeline/utils/` — hashing.py, logging.py, rate_limiter.py
- `verticals/hydraulic-filters/config.yaml` — Phase 1-5 search queries
- `requirements.txt` — anthropic, requests, bs4, praw, chromadb, pyyaml, click, rich, tenacity
- `.gitignore` — Excludes .env, DBs, snapshots
- `.env.example` — Template for API keys

### Sprint 1 status: COMPLETE ✅
Bootstrap tested and working:
```
oracle.db — fluids: 7 | artifacts: 0 | standards: 0 | products: 0
[bootstrap] Seeded 7 fluids, 21 property records, 24 compatibility records
[bootstrap] Seeded vertical: hydraulic-filters (16 parameters, 8 outcome fields)
```

---

## Architecture Decisions (Do Not Re-Litigate)

1. **Single oracle.db** — Not per-vertical databases. Operating context layer requires
   cross-vertical queries. Vertical isolation abandoned in favor of vertical_id tagging.

2. **Operating context is the fundamental unit** — Every consultation starts here.
   Fluid properties, system conditions, performance requirements, constraints.
   A single operating context (e.g., "15% NaOCl at 95°F, 2 GPM, 80 PSI") is legible
   to every vertical simultaneously.

3. **Script collects, LLM synthesizes** — Python does data collection. Anthropic API is
   called only for synthesis/tagging at end of phase, never for scraping.

4. **Fluid properties: tiered sourcing** — NIST WebBook for pure compounds, Engineering
   ToolBox for mixtures, vendor TDS (ExxonMobil Mobil DTE, Shell Tellus) for commercial oils.
   Source tracked per row in fluid_properties table. NIST alone is insufficient —
   mineral oil (most common hydraulic fluid) is not in NIST.

5. **Vector store: Chroma** — Portable, local, no server required.

6. **Vertical ontology: parameter registry** — vertical_parameters table. Adding a new
   vertical requires no schema migration, only new rows.

7. **Active forum participation: gated** — Human approval required per question/answer.
   Posting without completing research is a community goodwill risk. Active participation
   only after Phase 4 identifies specific gaps. Identity: project account (not personal,
   not pretending to be human).

8. **Forums to create accounts on now:**
   - Eng-Tips (eng-tips.com) — most important, Hydraulic & Pneumatic Engineering forum
   - Reddit — r/hydraulics, r/fluidpower

9. **Reddit API** — Erik has submitted access request. Free tier via reddit.com/prefs/apps.
   Pipeline falls back to Brave-indexed Reddit content until API credentials arrive.

10. **Git repo** — Erik will set up. Use .gitignore as written (excludes .env, DBs, snapshots).

---

## The Commissioning Module (Designed, Not Yet Implemented)

This is the most strategically important module. There is NO existing standard for
component-level performance verification. This is an opportunity to define one.

### Three-document structure (auto-generated from consultation record):

**Document 1: Installation Verification** (completed at startup, 5-10 min)
- Confirms model matches recommendation
- As-installed conditions vs. design conditions from consultation
- If measured conditions differ from design, flags potential performance issue

**Document 2: Performance Verification** (2-4 weeks post-startup, 10-15 min)
- Vertical-specific and application-specific (generated from vertical ontology)
- Gas cooling nozzle → evaporation questions
- Coating nozzle → uniformity questions
- Hydraulic filter → cleanliness code achieved questions

**Document 3: Longevity Report** (3, 6, 12 months — 3 questions, <60 seconds)
1. Is component still in service?
2. If replaced, failure mode? (vertical-specific taxonomy)
3. Would you select this same component again? ← THE most valuable data point

### Schema additions needed (NOT YET IMPLEMENTED):
- `commissioning_plans` — generated at recommendation time, links to consultation_id
- `installation_verifications` — Document 1 data
- `performance_verifications` — Document 2 data (vertical-specific parameters)
- `longevity_reports` — Document 3 (3/6/12 month cadence)
- `failure_mode_taxonomy` — per-vertical standardized failure modes (rows in vertical_outcome_templates)
- `vertical_parameters` needs: `is_verification_param`, `measurement_method`, `acceptable_deviation_pct`
- OpenClaw cron triggers per consultation: startup+21 days, +3 months, +6 months, +12 months

### The CPVP Standard strategy:
Name it "Component Performance Verification Protocol." Publish as open white paper BEFORE
significant platform adoption. Target: ILASS for nozzles, Hydraulic Institute for pumps/filters.
The framework is the Trojan horse; the platform is the implementation. Competitors can copy
the platform; they can't retroactively become the entity that defined the standard.

### User model for commissioning:
Email-only auth (already implemented in Spray Oracle). No passwords, no accounts layer needed.
Consultation ownership = email address. Reminder routing = same email.

---

## Documentation Strategy (Agreed, Not Yet Implemented)

When Erik shares the Spray Oracle repo, create these docs IN THAT REPO:

**Invariant context documents** (load first in any AI session, rarely change):
- `CONTEXT.md` — What/why document: project purpose, SpecialChem analog, business model,
  multi-vertical expansion thesis, CPVP commissioning strategy
- `SCHEMA.md` — Data model (already exists in pipeline repo, will need to live in main repo)
- `GLOSSARY.md` — Domain terms (Beta ratio, ISO 4406, µm vs µm(c)) + platform terms
  (vertical, consultation, operating context, commissioning event)
- `COMMISSIONING.md` — CPVP spec written as publishable document

**Operational documents** (updated with development):
- `ARCHITECTURE.md` — System overview
- `DECISIONS.md` — ADR log (what was decided, alternatives considered, rationale)
- `ROADMAP.md` — Sprint status and upcoming phases
- `verticals/*/README.md` — Per-vertical parameter rationale, key standards, known gaps

**Oracle-surface specific** (once repo is shared):
- `CONSULTATION_FLOW.md` — End-to-end: intake → retrieval → recommendation → commissioning trigger
- `KNOWLEDGE_INJECTION.md` — How pipeline output connects to Oracle (format, tables, context building)

---

## Schema Additions Pending (Do These Next)

Three things agreed upon but not yet written into db.py or SCHEMA.md:

1. **Consultation sharing model**
   - Add `is_public`, `is_anonymized` to `consultations` table
   - Add `consultation_library` concept (published cases = PCPartPicker's "completed builds")
   - Solves cold-start problem — each consultation adds value without requiring a community

2. **SEO content artifacts**
   - Pipeline has a second output: publication-ready technical content (selection guides,
     application notes, comparison articles) alongside Oracle knowledge base
   - Needs `content_artifacts` table and synthesis module

3. **Commissioning module tables** (detailed above)

---

## Rate Limits (Critical — Erik enforces this)

Anthropic API limits (apply across ALL sessions including sub-agents):
- 50 requests/min
- 30K input tokens/min  ← THIS is the binding constraint; long responses burn it fast
- 8K output tokens/min
- 50 batch requests/min
- 30 web search tool uses/min

**Model policy:**
- Opus: planning and architecture only, switch back to Sonnet immediately after
- Sonnet: everything else

Current session ended because context hit ~80%+. New session should start clean.

---

## Immediate Next Steps (In Order)

1. **Wait for Spray Oracle repo** — Erik will share. Read it before writing code.
   Understand existing consultation flow, auth system, how knowledge is injected.

2. **Write invariant docs** — CONTEXT.md and GLOSSARY.md once repo structure is known.

3. **Add commissioning module to schema** — db.py additions, vertical_parameters new fields,
   failure mode taxonomy rows for hydraulic-filters.

4. **Add consultation sharing model** — is_public/is_anonymized flags, library concept.

5. **Sprint 2: ISO catalog fetcher** — Direct crawl of iso.org TC/SC catalog pages.
   Phase 1 currently only does Brave search queries. ISO catalog direct fetch is the
   highest-value missing piece.

6. **Sprint 2: LLM tagger** — Batch-tags collected artifacts against vertical ontology.
   Single API call per batch: input = artifact content + parameter registry,
   output = vertical_tags + parameter_tags + fluid_tags.

7. **Sprint 2: Chroma integration** — vector_store.py wrapper. Chromadb already installed.

8. **Get .env set up** — Erik needs to drop API keys into .env (copy from .env.example).
   Brave API key is the unblock for running Phase 1. Reddit key pending Erik's application.

---

## Open Questions

1. When does the Oracle interface development fork from the pipeline development?
   The browser UI + API layer (confirmed by Erik) hasn't been started. At some point
   Sprint N needs to fork into two tracks.

2. Vertical #2 after hydraulic filters — follow user pull, not strategic planning.
   Watch what adjacent questions appear in the hydraulic filters Oracle consultations.

3. Forum identity / disclosure strategy — project account confirmed, but "about this account"
   profile statement needs to be written before any posting begins.

4. Spray Oracle repo structure — unknown until Erik shares. May require refactoring
   the pipeline's output format to match what the Oracle surface expects.

---

## Key People / Context

- **Erik Cullen** — Telegram ID 8666863850, Pacific Time
- **TheSprayOracle.com** — Existing product, nozzle vertical, Erik built it
- **SpecialChem** (specialchem.com) — Closest business model analog. Study deeply.
  Founded 2000 Paris, CEO Christophe Cabarry. 500K+ professionals, 350K+ products,
  3,800+ companies. Free for engineers, supplier-pays revenue model.
