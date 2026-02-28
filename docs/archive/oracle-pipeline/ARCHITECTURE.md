# Oracle Pipeline — System Architecture

**Version:** 0.1 (Draft)
**Date:** 2026-02-24
**Author:** OpenClaw / Erik Cullen
**Purpose:** Repeatable research pipeline for building domain-specific AI expert systems ("Oracles") across industrial fluid component verticals.

---

## 1. System Overview

The Oracle Pipeline is a **portable Python application** that OpenClaw orchestrates but does not depend on. It collects, structures, and synthesizes domain knowledge across 6 phases, producing a versioned knowledge base that feeds a prompted LLM (the "Oracle") for procurement and diagnostic support.

```
┌─────────────────────────────────────────────────────┐
│                  OpenClaw (Orchestrator)             │
│  - Launches pipeline runs                           │
│  - Monitors progress                                │
│  - Iterates and improves pipeline between runs      │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│              Oracle Pipeline (Python)                │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │Collectors│→ │Data Store│→ │Synthesizer (LLM) │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│       │              │               │              │
│  Python scripts  SQLite + JSON   Anthropic API      │
│  (requests,      (structured,    (synthesis only,   │
│   BeautifulSoup)  auditable)     not collection)    │
└─────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│              Knowledge Base (per vertical)           │
│  - Structured data (SQLite)                         │
│  - Source archive (raw HTML/PDF snapshots)           │
│  - Synthesized artifacts (markdown dossiers)         │
│  - Oracle system prompt + context documents          │
└─────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│           Cross-Vertical Reference Store             │
│  - Shared standards (ISO 4406 appears once)          │
│  - Shared concepts (Beta ratio, cleanliness codes)   │
│  - Vertical linkage graph                            │
└─────────────────────────────────────────────────────┘
```

### Design Principles

1. **Script collects, LLM synthesizes.** Data collection is Python. The Anthropic API is used only for analysis, synthesis, gap identification, and Oracle prompt generation. This minimizes API cost and maximizes reproducibility.
2. **Everything has provenance.** Every datum traces to a source URL, access date, collection method, and confidence level.
3. **Checkpoint everything.** Each phase writes intermediate results. A crash at Phase 4 loses zero work from Phases 1–3.
4. **Portable.** Runs anywhere with Python 3.11+ and an Anthropic API key. No OpenClaw dependency at runtime.
5. **Idempotent.** Re-running a phase skips already-collected sources (by URL hash) unless `--force` is passed.
6. **Cross-vertical aware.** Shared standards/concepts are stored once and linked, not duplicated.

---

## 2. Data Model

### 2.1 Core Schema (SQLite)

```sql
-- Every collected item, regardless of phase or type
CREATE TABLE sources (
    id              TEXT PRIMARY KEY,  -- SHA-256 of (url + vertical + phase)
    url             TEXT NOT NULL,
    url_hash        TEXT NOT NULL,     -- SHA-256 of URL alone (for dedup)
    vertical        TEXT NOT NULL,     -- e.g., "hydraulic-filters"
    phase           INTEGER NOT NULL,  -- 1-6
    source_type     TEXT NOT NULL,     -- "standards-catalog", "forum-thread", "vendor-catalog", etc.
    access_date     TEXT NOT NULL,     -- ISO 8601
    collection_method TEXT NOT NULL,   -- "brave-search", "direct-fetch", "api", "manual"
    http_status     INTEGER,
    raw_snapshot_path TEXT,            -- path to archived HTML/PDF
    extracted_text  TEXT,              -- cleaned text content
    metadata_json   TEXT,             -- source-type-specific structured data
    confidence      REAL DEFAULT 1.0, -- 0.0 to 1.0
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- Standards (Phase 1 primary output)
CREATE TABLE standards (
    id              TEXT PRIMARY KEY,  -- e.g., "ISO-4406-2021"
    standard_number TEXT NOT NULL,     -- e.g., "ISO 4406:2021"
    full_title      TEXT,
    issuing_body    TEXT NOT NULL,
    tc_sc           TEXT,              -- e.g., "TC 131/SC 6"
    what_it_governs TEXT,              -- one-sentence description
    current_version TEXT,
    supersedes      TEXT,              -- comma-separated old standard IDs
    status          TEXT DEFAULT 'active', -- active, superseded, withdrawn
    practitioner_relevance TEXT,       -- "primary", "secondary", "deprecated"
    vertical        TEXT,              -- NULL = cross-vertical
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Evidence linking standards to sources
CREATE TABLE standard_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_id     TEXT NOT NULL REFERENCES standards(id),
    source_id       TEXT NOT NULL REFERENCES sources(id),
    mention_type    TEXT NOT NULL,     -- "direct-citation", "discussion", "recommendation", "complaint"
    context_snippet TEXT,              -- relevant quote (≤500 chars)
    thread_reply_count INTEGER,       -- for forum sources
    author_expertise TEXT,             -- "experienced", "unknown", "vendor"
    UNIQUE(standard_id, source_id, mention_type)
);

-- Practitioner relevance scoring (computed from evidence)
CREATE TABLE standard_relevance (
    standard_id     TEXT NOT NULL REFERENCES standards(id),
    vertical        TEXT NOT NULL,
    independent_forum_mentions INTEGER DEFAULT 0,
    vendor_catalog_citations   INTEGER DEFAULT 0,
    relevance_tier  TEXT,              -- "primary" (≥5 forum OR ≥3 vendor), "secondary", "deprecated"
    computed_at     TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (standard_id, vertical)
);

-- Academic references (Phase 2)
CREATE TABLE academic_refs (
    id              TEXT PRIMARY KEY,
    ref_type        TEXT NOT NULL,     -- "textbook", "paper", "thesis", "course-syllabus"
    title           TEXT NOT NULL,
    authors         TEXT,
    year            INTEGER,
    publisher       TEXT,
    doi             TEXT,
    isbn            TEXT,
    syllabus_url    TEXT,
    practitioner_recommendation_count INTEGER DEFAULT 0,
    topics_covered  TEXT,              -- JSON array of topic tags
    vertical        TEXT,
    source_id       TEXT REFERENCES sources(id)
);

-- Vendor products (Phase 3)
CREATE TABLE vendors (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    website         TEXT,
    verticals       TEXT,              -- JSON array
    data_quality    TEXT,              -- "engineering", "marketing", "mixed"
    neutrality_flags TEXT,             -- JSON array of specific concerns
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE products (
    id              TEXT PRIMARY KEY,
    vendor_id       TEXT NOT NULL REFERENCES vendors(id),
    product_line    TEXT,
    product_type    TEXT,              -- taxonomy category
    specifications  TEXT,              -- JSON: ratings, dimensions, performance data
    standards_cited TEXT,              -- JSON array of standard_ids
    vertical        TEXT NOT NULL,
    source_id       TEXT REFERENCES sources(id)
);

-- Practitioner reasoning patterns (Phase 4)
CREATE TABLE reasoning_patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type    TEXT NOT NULL,     -- "selection", "sizing", "specification"
    summary         TEXT NOT NULL,
    reasoning_steps TEXT NOT NULL,     -- JSON array of ordered steps
    source_id       TEXT NOT NULL REFERENCES sources(id),
    author_expertise TEXT,
    upvotes         INTEGER,
    vertical        TEXT NOT NULL,
    standards_referenced TEXT,         -- JSON array of standard_ids
    confidence      REAL DEFAULT 1.0
);

-- Failure modes (Phase 5)
CREATE TABLE failure_modes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    failure_type    TEXT NOT NULL,     -- taxonomy category
    symptoms        TEXT NOT NULL,     -- JSON array
    root_causes     TEXT NOT NULL,     -- JSON array
    diagnostic_steps TEXT,             -- JSON array of ordered steps
    resolution      TEXT,
    source_id       TEXT NOT NULL REFERENCES sources(id),
    author_expertise TEXT,
    vertical        TEXT NOT NULL,
    confidence      REAL DEFAULT 1.0
);

-- Knowledge gaps (Phase 6)
CREATE TABLE gaps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_type        TEXT NOT NULL,     -- "thin-documentation", "sparse-forum", "vendor-conflict", "no-standard"
    description     TEXT NOT NULL,
    severity        TEXT NOT NULL,     -- "critical", "moderate", "minor"
    vertical        TEXT NOT NULL,
    suggested_action TEXT,             -- "forum-question", "expert-interview", "accept-gap"
    question_draft  TEXT,              -- for active forum participation
    status          TEXT DEFAULT 'open', -- "open", "addressed", "accepted"
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Validation cases (Phase 6)
CREATE TABLE validation_cases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_type       TEXT NOT NULL,     -- "selection", "diagnosis", "sizing"
    problem_statement TEXT NOT NULL,
    known_reasoning TEXT NOT NULL,     -- the expert's approach
    known_outcome   TEXT NOT NULL,
    source_id       TEXT NOT NULL REFERENCES sources(id),
    vertical        TEXT NOT NULL,
    oracle_tested   INTEGER DEFAULT 0,
    oracle_result   TEXT,
    oracle_score    REAL              -- 0.0 to 1.0 match quality
);

-- Cross-vertical concept linkage
CREATE TABLE concepts (
    id              TEXT PRIMARY KEY,  -- e.g., "beta-ratio", "cleanliness-code"
    name            TEXT NOT NULL,
    definition      TEXT,
    related_standards TEXT,            -- JSON array of standard_ids
    verticals       TEXT NOT NULL      -- JSON array of verticals that reference this
);

-- Pipeline run log (audit trail)
CREATE TABLE runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical        TEXT NOT NULL,
    phase           INTEGER NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    status          TEXT DEFAULT 'running', -- "running", "completed", "failed", "interrupted"
    sources_collected INTEGER DEFAULT 0,
    errors          TEXT,              -- JSON array of error descriptions
    config_snapshot TEXT,              -- JSON of config used for this run
    notes           TEXT
);
```

### 2.2 File System Layout

```
oracle-pipeline/
├── pipeline/                    # Python package
│   ├── __init__.py
│   ├── cli.py                   # Entry point: `python -m pipeline run --vertical hydraulic-filters --phase 1`
│   ├── config.py                # Vertical configs, API keys, source definitions
│   ├── db.py                    # SQLite operations
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── base.py              # Abstract collector with rate limiting, retries, provenance
│   │   ├── brave_search.py      # Brave Search API wrapper
│   │   ├── web_fetch.py         # Direct HTTP + BeautifulSoup extraction
│   │   ├── iso_catalog.py       # ISO TC/SC catalog crawler
│   │   ├── forum_scraper.py     # Eng-Tips, Reddit, etc.
│   │   ├── scholar.py           # Google Scholar / semantic scholar
│   │   ├── vendor_catalog.py    # Vendor website crawlers
│   │   └── archive.py           # Raw HTML/PDF snapshot archiver
│   ├── phases/
│   │   ├── __init__.py
│   │   ├── phase1_standards.py
│   │   ├── phase2_academic.py
│   │   ├── phase3_vendors.py
│   │   ├── phase4_reasoning.py
│   │   ├── phase5_failures.py
│   │   └── phase6_gaps.py
│   ├── synthesizer/
│   │   ├── __init__.py
│   │   ├── llm.py               # Anthropic API client (synthesis only)
│   │   ├── dossier.py           # Phase output document generation
│   │   ├── oracle_prompt.py     # Oracle system prompt builder
│   │   └── cross_vertical.py    # Cross-vertical linking logic
│   └── utils/
│       ├── __init__.py
│       ├── rate_limiter.py      # Token bucket rate limiter
│       ├── hashing.py           # URL/content hashing
│       └── logging.py           # Structured logging
├── verticals/
│   ├── hydraulic-filters/
│   │   ├── config.yaml          # Vertical-specific config (sources, search terms, etc.)
│   │   ├── data.db              # SQLite database
│   │   ├── snapshots/           # Raw HTML/PDF archives
│   │   ├── phase1/
│   │   │   ├── dossier.md       # Synthesized output
│   │   │   └── run.log          # Structured run log
│   │   ├── phase2/ ... phase6/
│   │   └── oracle/
│   │       ├── system_prompt.md
│   │       ├── context/         # Knowledge base documents for RAG/injection
│   │       └── validation/      # Test cases and results
│   └── pumps/
│       └── ...
├── shared/
│   ├── standards.db             # Cross-vertical standards database
│   ├── concepts.db              # Cross-vertical concept graph
│   └── forum_accounts.yaml      # Forum access credentials (gitignored)
├── requirements.txt
├── pyproject.toml
├── README.md
└── .env.example                 # API keys template
```

---

## 3. Phase Specifications

### Phase 1 — Standards and Regulatory Landscape

**Input:** Vertical config (which TC/SCs to search, which forums, which search terms)
**Output:** Populated `standards`, `standard_evidence`, `standard_relevance` tables + synthesized dossier

**Collection Steps (Python, no LLM):**

1. **ISO Catalog Crawl**
   - Fetch ISO TC/SC catalog page (e.g., TC 131/SC 6 for hydraulic filters)
   - Parse every standard listed: number, title, status, edition
   - Store in `standards` table with `source_type = "standards-catalog"`
   - Archive raw HTML

2. **Secondary Standards Bodies**
   - SAE: Search saemobilus.sae.org for relevant standards
   - NFPA (fluid power): Search nfpa.com catalog
   - DIN/EN: Check if absorbed into ISO or still independent
   - ASME: Where applicable
   - Store each with proper issuing_body attribution

3. **Forum Evidence Collection** (Brave Search → targeted fetch)
   - For each forum (Eng-Tips, Reddit):
     - Run predefined search queries via Brave API: `site:eng-tips.com "ISO 16889"`, etc.
     - Collect top N results per query
     - Fetch each thread page
     - Extract: thread title, reply count, date range, standards mentioned
     - For each standard mention: create `standard_evidence` row with context snippet
   - Rate limit: respect Brave API limits (30 searches/min allocation for Phase 1)

4. **Vendor Technical Documentation** (evidence only, not product data)
   - Search for vendor pages that cite standards (e.g., "ISO 4406 site:parker.com")
   - Extract which standards each vendor references in technical contexts
   - Create `standard_evidence` rows with `mention_type = "vendor-citation"`

**Synthesis Steps (LLM):**
- After all collection is complete, call Anthropic API once to:
  - Review the structured data
  - Generate the dossier markdown following the output schema
  - Identify gaps and surprises
  - Flag any standards found in forums that weren't in the ISO catalog crawl

**Relevance Computation (Python, no LLM):**
- Count independent forum mentions per standard
- Count vendor catalog citations per standard
- Apply thresholds: ≥5 forum mentions OR ≥3 vendor citations → "primary"
- This is deterministic, not LLM-judged

**Estimated Resources:**
- Brave API calls: ~50-80 searches
- Direct web fetches: ~100-200 pages
- Anthropic API: 1-3 calls for synthesis (~20K input tokens, ~5K output tokens)
- Wall clock: 15-30 minutes
- API cost: <$2

---

### Phase 2 — Academic and Textbook Foundation

**Input:** Standards data from Phase 1 (for vocabulary/keyword generation)
**Output:** Populated `academic_refs` table + synthesized bibliography

**Collection Steps:**

1. **Google Scholar / Semantic Scholar**
   - Generate search queries from Phase 1 standards (e.g., "hydraulic filter Beta ratio", "multi-pass filter testing ISO 16889")
   - Collect paper metadata: title, authors, year, citation count, DOI
   - No full-text download (copyright)

2. **University Course Syllabi**
   - Search: `"hydraulic systems" syllabus filetype:pdf site:edu`
   - Search: `"fluid power" course outline site:edu`
   - Extract textbook references from syllabi

3. **Publisher Catalogs**
   - Search Springer, Elsevier, Wiley for relevant textbooks
   - Extract metadata only

4. **Forum Book Recommendations**
   - Search forums: `"best book" "hydraulic" site:eng-tips.com`
   - Search: `"recommended reading" "filtration" site:reddit.com`
   - Extract book titles and recommendation context

**Synthesis:** LLM reviews collected references, ranks by relevance, identifies core texts vs. niche references, produces annotated bibliography.

---

### Phase 3 — Vendor Landscape and Product Architecture

**Input:** Standards vocabulary (Phase 1), technical concepts (Phase 2)
**Output:** Populated `vendors`, `products` tables + vendor landscape report

**Collection Steps:**

1. **Vendor Identification**
   - Use Brave search to identify major vendors for the vertical
   - Forum threads: "best [component] manufacturer" type queries
   - Industry directories where available

2. **Catalog Crawling**
   - For each identified vendor: crawl product catalog pages
   - Extract product taxonomy, specifications, standards cited
   - Assess data quality: does the vendor publish real ISO 16889 test data, or just "10 micron nominal"?
   - Archive catalog pages

3. **Vendor Comparison Threads**
   - Forum search for vendor comparison discussions
   - Extract: which vendors, what criteria, what conclusions
   - Flag vendor disagreements (Beta 1000 vs Beta 5000 for same micron rating)

**Synthesis:** LLM produces vendor landscape report, product taxonomy, neutrality flags.

---

### Phase 4 — Selection Criteria and Practitioner Reasoning

**Input:** All of Phases 1-3 (standards vocabulary, technical concepts, vendor landscape)
**Output:** Populated `reasoning_patterns` table + selection logic documentation

**Collection Steps:**

1. **Heavy Forum Scraping**
   - Search for selection/sizing/specification threads
   - Queries: "how to select [component]", "sizing [component] for", "specifying [component]"
   - For each thread with expert responses:
     - Extract the reasoning sequence (not just the answer)
     - Tag which standards/concepts are referenced
     - Rate author expertise (post count, star rating where visible)

2. **Application Notes and White Papers**
   - Vendor application guides (these often contain genuine selection methodology)
   - Industry association guides

**Synthesis:** LLM extracts reasoning patterns from forum threads. This is where LLM judgment is most valuable — recognizing the difference between "use 10 micron" and the full reasoning chain.

---

### Phase 5 — Failure Modes and Diagnostic Knowledge

**Input:** All of Phases 1-4
**Output:** Populated `failure_modes` table + diagnostic decision tree documentation

**Collection Steps:**

1. **Failure Story Threads**
   - Forum search: "[component] failure", "[component] problem", "premature failure"
   - Extract: symptoms, root cause analysis, resolution
   - Tag failure type taxonomy

2. **Manufacturer Troubleshooting Guides**
   - Vendor troubleshooting documentation
   - Technical bulletins

**Synthesis:** LLM organizes failure modes into diagnostic trees (symptom → possible causes → diagnostic steps → resolution).

---

### Phase 6 — Gap Analysis and Validation

**Input:** All of Phases 1-5
**Output:** Populated `gaps` and `validation_cases` tables + gap report + validation suite

**Collection:** Primarily LLM analysis of existing data, not new web collection.

**Steps:**

1. **Gap Identification (LLM)**
   - Review all tables for thin coverage areas
   - Identify vendor conflicts without resolution
   - Flag topics with no forum coverage
   - Draft questions for active forum participation (gated — requires human approval)

2. **Validation Case Extraction (LLM)**
   - Identify forum threads with complete problem → reasoning → outcome chains
   - Structure as test cases for the Oracle

3. **Oracle Prompt Generation (LLM)**
   - Using all collected knowledge, generate:
     - System prompt with vendor neutrality flags
     - Context documents organized by topic
     - Selection methodology reference
     - Diagnostic decision tree reference

---

## 4. Cross-Vertical Knowledge Management

### Strategy: Shared Reference Store with Vertical Linking

When a collector encounters a standard, concept, or source that already exists in the shared store:

1. **Check shared DB first** (by standard number or concept ID)
2. **If exists:** Create a link from the vertical to the shared entity. Add any new evidence specific to this vertical.
3. **If new:** Create in shared DB. Mark which verticals reference it.

This means ISO 4406 is researched deeply once (during the first vertical that encounters it) and subsequent verticals inherit that knowledge while adding vertical-specific context.

### Implementation

```python
# In db.py
def get_or_create_standard(standard_number: str, vertical: str) -> str:
    """Check shared standards DB first, then vertical DB."""
    shared = shared_db.get_standard(standard_number)
    if shared:
        # Link this vertical to existing standard
        shared_db.add_vertical_link(shared.id, vertical)
        return shared.id
    else:
        # Create new standard in shared DB
        return shared_db.create_standard(standard_number, vertical)
```

### Cross-Vertical Oracle

When verticals are mature enough to combine:
- The Oracle prompt builder can pull from multiple vertical knowledge bases
- Context injection prioritizes the primary vertical but includes cross-references
- Example: A hydraulic system question might pull from filters, pumps, and valves verticals

---

## 5. Rate Limiting and Resource Management

### Brave Search API
- Budget: 30 calls/min (shared with OpenClaw)
- Pipeline allocation: 20 calls/min max (reserve 10 for OpenClaw interactive use)
- Implemented as token bucket in `rate_limiter.py`

### Anthropic API
- Budget: 50 requests/min, 30K input tokens/min, 8K output tokens/min
- Pipeline allocation: synthesis calls only, batched at end of each phase
- Estimated per-phase: 1-5 API calls
- Estimated per-vertical (all 6 phases): 15-30 API calls, ~100K input tokens, ~30K output tokens

### Web Fetching
- Polite crawling: 1 request/second per domain
- Respect robots.txt
- User-Agent: honest identification (not pretending to be a browser)
- Retry with exponential backoff on 429/503

### Forum-Specific Limits
- Eng-Tips: No API. Scrape via Brave cached/indexed content first. Direct fetch only for threads identified as high-value. Rate limit: 1 req/5 seconds.
- Reddit: Use Reddit API (requires app registration). Rate limit per Reddit API terms.
- Other forums: Assess per-forum. Default to Brave index first.

---

## 6. Active Forum Participation (Gated)

### Design

The `gaps` table has a `question_draft` field. When Phase 6 identifies a gap suitable for a forum question:

1. LLM drafts a question that demonstrates existing knowledge
2. Question is stored in `gaps` table with `status = "open"`
3. **Human review required** — pipeline never posts without approval
4. Approved questions are queued in `forum_questions` table
5. Posting module formats for the target forum's conventions
6. Response monitoring: periodic check for replies (cron job)

### Forum Question Lifecycle

```
Draft → Review → Approved → Posted → Monitoring → Replies Ingested → Closed
  │        │         │          │          │              │
  │        │         │          │          │              └─ LLM extracts knowledge,
  │        │         │          │          │                 updates relevant tables
  │        │         │          │          │
  │        │         │          │          └─ Cron job checks thread for new replies
  │        │         │          │             (OpenClaw cron, configurable interval)
  │        │         │          │
  │        │         │          └─ Post to forum, record thread URL + post date
  │        │         │
  │        │         └─ Human approves (may edit question first)
  │        │
  │        └─ Human reviews draft, may reject or request revision
  │
  └─ Phase 6 LLM drafts question from identified gap
```

### Database Support

```sql
-- Forum question tracking (extends gaps table)
CREATE TABLE forum_questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_id          INTEGER NOT NULL REFERENCES gaps(id),
    vertical        TEXT NOT NULL,
    target_forum    TEXT NOT NULL,     -- "eng-tips", "reddit-hydraulics", etc.
    target_subforum TEXT,              -- specific subforum/subreddit
    question_draft  TEXT NOT NULL,     -- LLM-drafted question
    question_final  TEXT,              -- human-edited version (if modified)
    status          TEXT DEFAULT 'draft',  -- draft, approved, posted, monitoring, ingested, closed
    approved_at     TEXT,
    approved_by     TEXT,              -- human who approved
    posted_at       TEXT,
    thread_url      TEXT,              -- URL of the posted thread
    thread_id       TEXT,              -- forum-native thread ID (for API polling)
    last_checked_at TEXT,
    reply_count     INTEGER DEFAULT 0,
    last_reply_at   TEXT,
    follow_up_needed INTEGER DEFAULT 0, -- flag for LLM to draft follow-up or thank-you
    closed_at       TEXT,
    close_reason    TEXT,              -- "answered", "no-response", "low-quality", "withdrawn"
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Individual replies tracked for ingestion
CREATE TABLE forum_replies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id     INTEGER NOT NULL REFERENCES forum_questions(id),
    reply_author    TEXT,
    reply_date      TEXT,
    reply_text      TEXT NOT NULL,
    author_expertise TEXT,             -- "experienced", "unknown", "vendor"
    ingested        INTEGER DEFAULT 0, -- has this been processed into knowledge base?
    ingested_at     TEXT,
    knowledge_type  TEXT,              -- what table(s) did this feed? "reasoning_pattern", "failure_mode", etc.
    knowledge_ids   TEXT,              -- JSON array of IDs created from this reply
    source_id       TEXT REFERENCES sources(id),  -- provenance link
    created_at      TEXT DEFAULT (datetime('now'))
);
```

### Monitoring via OpenClaw Cron

Once a question is posted, the pipeline registers an OpenClaw cron job to monitor the thread:

```python
# In forum_monitor.py
def register_monitor(question_id: int, thread_url: str, forum: str):
    """Register a cron job to check this thread for new replies."""
    # Check interval: every 6 hours for first week, daily after that, 
    # weekly after 30 days, stop after 90 days with no new replies
    schedule = compute_decay_schedule(posted_at=datetime.now())
    
    # OpenClaw cron job that:
    # 1. Fetches the thread page
    # 2. Compares reply count to last known
    # 3. If new replies: extracts them, stores in forum_replies table
    # 4. Notifies human via OpenClaw message: "New reply on your [vertical] question about [topic]"
    # 5. If reply looks substantive, flags for knowledge ingestion
```

The monitoring loop:
1. **Fetch** — cron job fetches the thread (respecting rate limits)
2. **Diff** — compare to last known state, extract new replies
3. **Notify** — alert human that new replies exist (via Telegram/webchat)
4. **Triage** — LLM assesses: is this reply substantive enough to ingest?
5. **Ingest** — if yes, extract knowledge and create rows in the appropriate phase tables (reasoning_patterns, failure_modes, etc.) with full provenance back to the forum reply
6. **Follow-up** — if the reply asks a clarifying question or the answer is partial, LLM drafts a follow-up (human approval required again)
7. **Close** — after the question is answered or monitoring expires, mark closed

### Decay Schedule

Forum threads have a natural lifecycle. Fresh threads get rapid replies, then activity dies off. The monitoring schedule mirrors this:

| Time since posting | Check interval |
|---|---|
| 0-48 hours | Every 6 hours |
| 2-7 days | Every 12 hours |
| 1-4 weeks | Daily |
| 1-3 months | Weekly |
| >3 months no reply | Close monitoring |

### Safeguards

- **No automated posting** without explicit human approval per question
- **No automated follow-up posting** without explicit human approval
- **Identity disclosure strategy** must be decided before any posting (TBD with Erik)
- **Quality gate:** LLM self-evaluates: "Would an experienced engineer find this question worth answering?"
- **Dedup:** Check if the question has already been asked (search before posting)
- **Gratitude:** When a question is answered well, LLM drafts a thank-you reply (human-approved) — this is both good etiquette and builds community trust
- **Withdrawal:** If a question was poorly received, human can mark it for deletion/withdrawal

---

## 7. Audit Trail

Every pipeline action is logged:

```python
# Structured log entry
{
    "timestamp": "2026-02-24T14:30:00Z",
    "vertical": "hydraulic-filters",
    "phase": 1,
    "action": "fetch",
    "url": "https://www.iso.org/committee/5069/x/catalogue/",
    "method": "direct-fetch",
    "http_status": 200,
    "items_extracted": 34,
    "duration_ms": 1250,
    "error": null
}
```

Run-level audit:
- Config snapshot at run start (what parameters were used)
- Source count per phase
- Error count and descriptions
- Total API calls and tokens used
- Wall clock time

This enables:
- "When was this data collected?" → check `sources.access_date`
- "Where did this claim come from?" → follow `source_id` to URL and snapshot
- "Has this been updated since the standard was revised?" → check `access_date` vs. standard revision date

---

## 8. Oracle System Prompt Architecture

The pipeline's final output per vertical is an Oracle — a prompted LLM with injected context. Structure:

```
Oracle System Prompt
├── Identity and Role
│   "You are a domain expert in [vertical]. You help engineers with
│    procurement decisions and diagnostic problem-solving."
├── Vendor Neutrality Statement
│   "You do not recommend specific vendors. When vendor-specific data
│    is relevant, present data from multiple vendors for comparison.
│    Known vendor data discrepancies: [flags from Phase 3]"
├── Standards Reference
│   Injected from Phase 1 dossier (primary standards with descriptions)
├── Selection Methodology
│   Injected from Phase 4 (reasoning patterns, not just answers)
├── Diagnostic Framework
│   Injected from Phase 5 (failure mode → diagnostic tree)
├── Known Limitations
│   Injected from Phase 6 (gaps, areas of thin coverage)
└── Citation Requirement
    "When providing technical guidance, cite the relevant standard
     or source. If you are uncertain, say so."
```

Context documents (for RAG or direct injection depending on context window):
- Full standards reference (Phase 1)
- Key textbook summaries (Phase 2)
- Vendor landscape with specifications (Phase 3, neutralized)
- Selection case studies (Phase 4)
- Failure mode database (Phase 5)

---

## 9. Implementation Plan

### Sprint 1: Foundation (Estimated: 2-3 days)
- [ ] Project scaffolding (pyproject.toml, directory structure)
- [ ] SQLite schema creation and db.py
- [ ] Base collector class with rate limiting, retry, provenance
- [ ] Brave Search collector
- [ ] Web fetch collector with archiving
- [ ] CLI entry point
- [ ] Logging infrastructure

### Sprint 2: Phase 1 Complete (Estimated: 2-3 days)
- [ ] ISO catalog collector
- [ ] Forum scraper (Eng-Tips via Brave, Reddit via API)
- [ ] SAE/NFPA catalog collectors
- [ ] Phase 1 orchestrator (runs all collectors in sequence)
- [ ] Relevance computation (deterministic)
- [ ] LLM synthesizer for dossier generation
- [ ] Test with hydraulic-filters vertical
- [ ] Compare output to existing dossier, validate improvement

### Sprint 3: Phases 2-3 (Estimated: 3-4 days)
- [ ] Google Scholar / Semantic Scholar collector
- [ ] University syllabus collector
- [ ] Vendor catalog crawler
- [ ] Phase 2 and 3 orchestrators
- [ ] Cross-vertical reference store

### Sprint 4: Phases 4-6 (Estimated: 3-4 days)
- [ ] Heavy forum scraping with reasoning extraction
- [ ] Failure mode extraction
- [ ] Gap analysis module
- [ ] Validation case extraction
- [ ] Oracle prompt generator

### Sprint 5: Polish and Second Vertical (Estimated: 2-3 days)
- [ ] Run full pipeline on second vertical (pumps)
- [ ] Identify and fix assumptions that were hydraulic-filter-specific
- [ ] Cross-vertical linking validation
- [ ] Documentation

**Total estimated: 12-17 days of development**

---

## 10. Decisions Log

1. **Reddit API:** Erik has submitted a request for API access. Free tier registration is a manual form at reddit.com/prefs/apps — no automated shortcut exists. Pipeline will use the API once credentials arrive; fall back to Brave-indexed Reddit content in the interim. *Implication: Phase 2-5 Reddit collection is unblocked via Brave fallback; full Reddit API integration added to Sprint 1 as a conditional module.*

2. **Forum identity:** A dedicated project account will be used for active forum participation. *Implication: Account creation, profile setup, and disclosure strategy (how to represent the account to forum communities) must be decided before any posting. Recommend a brief "about this account" profile statement that is honest without being off-putting. To be designed separately.*

3. **Oracle deployment:** Browser interface as primary UI, with API access to saved content for programmatic users. *Implication: The knowledge base needs a REST API layer in addition to the Oracle chat interface. The pipeline output format must be API-consumable (structured JSON/SQLite) not just markdown. Oracle context injection should work both for chat (RAG) and for API queries (structured lookup). This adds a Sprint 6: API layer and browser UI scaffolding.*

4. **Version control:** Git repo will be set up by Erik. *Implication: Pipeline code should be written assuming git from the start — .gitignore for secrets/snapshots, clean commit history, meaningful commit messages. I will structure the project accordingly and avoid committing API keys, raw HTML snapshots, or the SQLite databases (those belong in .gitignore).*

5. **First vertical:** Confirmed — hydraulic filters, full Phases 1-6, before moving to the next vertical.
