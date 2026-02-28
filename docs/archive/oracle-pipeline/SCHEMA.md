# Oracle Platform — Revised Schema Design

**Version:** 0.2
**Date:** 2026-02-24
**Supersedes:** Vertical-siloed schema in ARCHITECTURE.md v0.1

---

## Design Principles

1. **Operating context is the fundamental unit.** Every consultation starts with a description of physical reality. The schema captures that once and makes it legible to every vertical.
2. **Fluid identity resolves to physical properties.** Store "15% NaOCl at 95°F" as an identity reference; derive viscosity, density, compatibility from a reference database.
3. **Verticals are extensible without schema changes.** Each vertical registers its parameter set. Adding a sixth vertical requires no migration.
4. **Knowledge artifacts have two representations.** Metadata and provenance in SQLite (queryable, auditable). Content in a vector store (semantically retrievable). These are linked by artifact ID.
5. **Products have curves, not just specs.** Performance is a function of operating conditions, not a single value.
6. **Consultations capture reasoning, not just answers.** The reasoning chain is the training data.
7. **Everything is single-database.** The operating context layer requires cross-vertical queries. Per-vertical isolation is abandoned in favor of vertical tagging on shared tables.

---

## Database Layout

```
oracle/
├── oracle.db          # Single unified SQLite database
├── vector/            # Chroma or similar — content embeddings
│   └── artifacts/     # One collection per artifact type
└── snapshots/         # Raw HTML/PDF archives (not in DB)
```

---

## Layer 1: Fluid Reference Database

The foundation. Resolves fluid identity to physical properties at specific conditions.

```sql
-- Known fluids (identity)
CREATE TABLE fluids (
    id              TEXT PRIMARY KEY,  -- slug: "sodium-hypochlorite", "mineral-oil-iso-46"
    name            TEXT NOT NULL,
    cas_number      TEXT,
    chemical_family TEXT,              -- "oxidizing-acid", "petroleum-oil", "water-glycol", etc.
    description     TEXT,
    hazard_class    TEXT,              -- GHS hazard classification
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Physical properties at specific conditions (temperature + concentration)
-- Populated from NIST, CRC Handbook, vendor data, or computed from correlations
CREATE TABLE fluid_properties (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fluid_id            TEXT NOT NULL REFERENCES fluids(id),
    concentration_pct   REAL,          -- NULL = pure fluid
    temperature_f       REAL NOT NULL,
    viscosity_dynamic_cp REAL,         -- centipoise
    viscosity_kinematic_cst REAL,      -- centistokes
    density_lb_gal      REAL,
    vapor_pressure_psia REAL,
    ph                  REAL,
    specific_heat_btu_lb_f REAL,
    bulk_modulus_psi    REAL,
    source              TEXT,          -- "NIST", "CRC-Handbook", "vendor:Parker", "correlation:Andrade"
    confidence          REAL DEFAULT 1.0,
    notes               TEXT
);
CREATE INDEX idx_fluid_props ON fluid_properties(fluid_id, temperature_f, concentration_pct);

-- Material compatibility per fluid
CREATE TABLE fluid_compatibility (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fluid_id            TEXT NOT NULL REFERENCES fluids(id),
    concentration_max_pct REAL,        -- NULL = any concentration
    temperature_max_f   REAL,          -- upper limit for this rating
    material            TEXT NOT NULL, -- "316SS", "Buna-N", "PTFE", "carbon-steel", etc.
    rating              TEXT NOT NULL, -- "excellent", "good", "fair", "poor", "incompatible"
    source_artifact_id  TEXT,          -- provenance
    notes               TEXT
);
CREATE INDEX idx_compat ON fluid_compatibility(fluid_id, material);
```

---

## Layer 2: Operating Context

Captures the engineer's physical reality once. All verticals read from the same record.

```sql
-- Root context record
CREATE TABLE operating_contexts (
    id              TEXT PRIMARY KEY,  -- UUID
    label           TEXT,              -- optional human label: "WWTP-Dosing-System-A"
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- The fluid(s) in this system
CREATE TABLE context_fluids (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    context_id          TEXT NOT NULL REFERENCES operating_contexts(id),
    fluid_id            TEXT NOT NULL REFERENCES fluids(id),
    concentration_pct   REAL,
    temperature_f       REAL NOT NULL,
    -- Solid/particulate loading
    carries_solids      INTEGER DEFAULT 0,
    solid_type          TEXT,          -- "abrasive", "fibrous", "soft", "biological"
    solid_loading_mg_l  REAL,
    particle_size_d50_um REAL,
    particle_size_max_um REAL,
    -- Derived properties (denormalized for query performance, computed from fluid_properties)
    resolved_viscosity_cst REAL,
    resolved_density_lb_gal REAL,
    resolved_ph         REAL,
    properties_resolved_at TEXT
);

-- System conditions
CREATE TABLE context_system_conditions (
    context_id          TEXT PRIMARY KEY REFERENCES operating_contexts(id),
    flow_rate_gpm       REAL,
    flow_profile        TEXT,          -- "continuous", "intermittent", "pulsating"
    inlet_pressure_psi  REAL,
    outlet_pressure_psi REAL,
    differential_pressure_psi REAL,
    pipe_size_inches    REAL,
    pipe_schedule       TEXT,
    ambient_temp_f      REAL,
    installation        TEXT,          -- "indoor", "outdoor", "submerged"
    vibration_level     TEXT,          -- "none", "low", "moderate", "high"
    regulatory          TEXT,          -- "none", "fda-food", "fda-pharma", "atex", "nsf61"
    notes               TEXT
);

-- Performance requirements (what the engineer needs to achieve)
-- Stored as a flexible key-value set against the vertical's parameter registry
CREATE TABLE context_requirements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    context_id      TEXT NOT NULL REFERENCES operating_contexts(id),
    vertical_id     TEXT NOT NULL,     -- which vertical this requirement is for
    parameter_key   TEXT NOT NULL,     -- from vertical_parameters.parameter_key
    value_numeric   REAL,
    value_text      TEXT,
    operator        TEXT DEFAULT '>=', -- ">=", "<=", "=", "range"
    value_max       REAL,              -- for range operator
    notes           TEXT
);

-- Hard constraints
CREATE TABLE context_constraints (
    context_id          TEXT PRIMARY KEY REFERENCES operating_contexts(id),
    max_height_in       REAL,
    max_width_in        REAL,
    max_depth_in        REAL,
    approved_materials  TEXT,          -- JSON array: ["316SS", "PTFE", "HDPE"]
    excluded_materials  TEXT,          -- JSON array
    approved_vendors    TEXT,          -- JSON array of manufacturer IDs
    excluded_vendors    TEXT,          -- JSON array
    budget_usd          REAL,
    weight_limit_lb     REAL,
    integration_notes   TEXT           -- existing infrastructure constraints
);
```

---

## Layer 3: Vertical Ontology

Extensible registry. Adding a new vertical requires no schema migration — only new rows.

```sql
-- Vertical definitions
CREATE TABLE verticals (
    id              TEXT PRIMARY KEY,  -- "hydraulic-filters", "pumps", "nozzles", "valves"
    display_name    TEXT NOT NULL,
    description     TEXT,
    active          INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Parameter registry per vertical
-- Each row defines one selectable/specifiable parameter for that vertical
CREATE TABLE vertical_parameters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    parameter_key   TEXT NOT NULL,     -- machine-readable: "beta_ratio_10um", "spray_angle_deg"
    display_name    TEXT NOT NULL,     -- human-readable: "Beta Ratio at 10µm"
    data_type       TEXT NOT NULL,     -- "float", "integer", "text", "boolean", "curve"
    unit            TEXT,              -- "µm", "GPM", "PSI", "°F", "-" (dimensionless)
    valid_min       REAL,
    valid_max       REAL,
    allowed_values  TEXT,              -- JSON array for enum types
    description     TEXT,
    required_for_selection INTEGER DEFAULT 0,
    UNIQUE(vertical_id, parameter_key)
);

-- Outcome templates — what to capture when engineer reports back
CREATE TABLE vertical_outcome_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    parameter_key   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    data_type       TEXT NOT NULL,
    description     TEXT,
    UNIQUE(vertical_id, parameter_key)
);
```

**Bootstrap data for hydraulic-filters vertical:**

```
vertical_parameters rows (sample):
  (hydraulic-filters, "cleanliness_target_iso4406", "Target ISO 4406 Code", "text", "-")
  (hydraulic-filters, "beta_ratio_required", "Required Beta Ratio", "float", "-", 2, 2000)
  (hydraulic-filters, "filter_micron_rating", "Filter Micron Rating", "float", "µm(c)", 1, 100)
  (hydraulic-filters, "system_flow_rate_gpm", "System Flow Rate", "float", "GPM", 0.1, 5000)
  (hydraulic-filters, "operating_viscosity_cst", "Operating Viscosity", "float", "cSt", 5, 1000)
  (hydraulic-filters, "filter_location", "Filter Location in Circuit", "text", "-")
  (hydraulic-filters, "bypass_valve_setting_psi", "Bypass Valve Setting", "float", "PSI")
  (hydraulic-filters, "element_collapse_pressure_psi", "Element Collapse Pressure", "float", "PSI")
  (hydraulic-filters, "fluid_type", "Hydraulic Fluid Type", "text", "-")
```

---

## Layer 4: Knowledge Base Index

Metadata layer connecting unstructured knowledge to the ontology.
Content lives in the vector store; this table is the index.

```sql
-- Every collected knowledge artifact
CREATE TABLE knowledge_artifacts (
    id              TEXT PRIMARY KEY,  -- content hash (dedup by content)
    title           TEXT,
    artifact_type   TEXT NOT NULL,     -- "forum-thread", "vendor-catalog", "standard",
                                       -- "textbook", "paper", "application-note",
                                       -- "course-syllabus", "technical-bulletin"
    source_url      TEXT NOT NULL,
    access_date     TEXT NOT NULL,
    collection_phase INTEGER,          -- which pipeline phase collected this (1-6)
    collection_method TEXT NOT NULL,   -- "brave-search", "direct-fetch", "reddit-api", "manual"
    authority_score REAL DEFAULT 0.5,  -- 0.0 (unknown forum post) to 1.0 (ISO standard)
    author          TEXT,
    author_expertise TEXT,             -- "experienced-engineer", "vendor", "unknown", "academic"
    publication_date TEXT,
    raw_snapshot_path TEXT,
    vector_id       TEXT,              -- ID in vector store
    tagging_method  TEXT,              -- "manual", "llm-automated", "rule-based"
    tagging_model   TEXT,              -- which LLM version if automated
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Which verticals does this artifact address?
CREATE TABLE artifact_vertical_tags (
    artifact_id     TEXT NOT NULL REFERENCES knowledge_artifacts(id),
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    relevance_score REAL DEFAULT 1.0,  -- 0.0 to 1.0
    tagged_by       TEXT,              -- human ID or "llm"
    tagged_at       TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (artifact_id, vertical_id)
);

-- Which operating context parameters does this artifact address?
CREATE TABLE artifact_parameter_tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id     TEXT NOT NULL REFERENCES knowledge_artifacts(id),
    vertical_id     TEXT NOT NULL,
    parameter_key   TEXT NOT NULL,
    tag_type        TEXT NOT NULL,     -- "addresses", "mentions", "constraints"
    tagged_by       TEXT,
    tagged_at       TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (vertical_id, parameter_key) REFERENCES vertical_parameters(vertical_id, parameter_key)
);

-- Which fluids does this artifact discuss?
CREATE TABLE artifact_fluid_tags (
    artifact_id     TEXT NOT NULL REFERENCES knowledge_artifacts(id),
    fluid_id        TEXT NOT NULL REFERENCES fluids(id),
    context         TEXT DEFAULT 'mentioned', -- "primary", "mentioned", "compatibility-data"
    PRIMARY KEY (artifact_id, fluid_id)
);

-- Standards are a specialized artifact type with extra metadata
CREATE TABLE standards (
    id              TEXT PRIMARY KEY,  -- e.g., "ISO-4406-2021"
    standard_number TEXT NOT NULL UNIQUE,
    full_title      TEXT,
    issuing_body    TEXT NOT NULL,
    tc_sc           TEXT,
    what_it_governs TEXT,
    current_version TEXT,
    supersedes      TEXT,              -- comma-separated standard IDs
    status          TEXT DEFAULT 'active',
    artifact_id     TEXT REFERENCES knowledge_artifacts(id)
);

-- Evidence of practitioner citations (feeds relevance scoring)
CREATE TABLE standard_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_id     TEXT NOT NULL REFERENCES standards(id),
    artifact_id     TEXT NOT NULL REFERENCES knowledge_artifacts(id),
    mention_type    TEXT NOT NULL,     -- "direct-citation", "discussion", "recommendation"
    context_snippet TEXT,
    thread_reply_count INTEGER,
    UNIQUE(standard_id, artifact_id, mention_type)
);

-- Computed relevance (deterministic, not LLM-judged)
CREATE TABLE standard_relevance (
    standard_id                TEXT NOT NULL REFERENCES standards(id),
    vertical_id                TEXT NOT NULL REFERENCES verticals(id),
    independent_forum_mentions INTEGER DEFAULT 0,
    vendor_catalog_citations   INTEGER DEFAULT 0,
    relevance_tier             TEXT,   -- "primary" (≥5 forum OR ≥3 vendor), "secondary", "deprecated"
    computed_at                TEXT,
    PRIMARY KEY (standard_id, vertical_id)
);

-- Academic references
CREATE TABLE academic_refs (
    id              TEXT PRIMARY KEY,
    ref_type        TEXT NOT NULL,     -- "textbook", "paper", "thesis", "course-syllabus"
    title           TEXT NOT NULL,
    authors         TEXT,
    year            INTEGER,
    publisher       TEXT,
    doi             TEXT,
    isbn            TEXT,
    practitioner_recommendation_count INTEGER DEFAULT 0,
    topics_covered  TEXT,              -- JSON array
    artifact_id     TEXT REFERENCES knowledge_artifacts(id)
);
```

---

## Layer 5: Products

```sql
-- Manufacturers
CREATE TABLE manufacturers (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    website         TEXT,
    data_quality    TEXT,              -- "engineering", "marketing", "mixed"
    neutrality_flags TEXT,             -- JSON array of specific concerns
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Products
CREATE TABLE products (
    id              TEXT PRIMARY KEY,
    manufacturer_id TEXT NOT NULL REFERENCES manufacturers(id),
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    model_number    TEXT NOT NULL,
    product_line    TEXT,
    display_name    TEXT,
    product_type    TEXT,              -- vertical-specific taxonomy
    active          INTEGER DEFAULT 1, -- still in production?
    artifact_id     TEXT REFERENCES knowledge_artifacts(id),
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Static specifications — maps to vertical_parameters
CREATE TABLE product_static_specs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      TEXT NOT NULL REFERENCES products(id),
    parameter_key   TEXT NOT NULL,
    value_numeric   REAL,
    value_text      TEXT,
    unit            TEXT,
    source_artifact_id TEXT REFERENCES knowledge_artifacts(id),
    confidence      REAL DEFAULT 1.0
);

-- Performance curves (e.g., flow vs pressure, dP vs flow, efficiency vs flow)
CREATE TABLE product_performance_curves (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          TEXT NOT NULL REFERENCES products(id),
    curve_type          TEXT NOT NULL,  -- "flow-vs-pressure", "dp-vs-flow", "efficiency-vs-flow"
    x_parameter         TEXT NOT NULL,  -- parameter_key for x-axis
    x_unit              TEXT,
    y_parameter         TEXT NOT NULL,  -- parameter_key for y-axis
    y_unit              TEXT,
    operating_conditions TEXT,          -- JSON: fixed conditions for this curve
                                        -- e.g., {"viscosity_cst": 32, "fluid": "mineral-oil"}
    source_artifact_id  TEXT REFERENCES knowledge_artifacts(id)
);

-- Points on a performance curve
CREATE TABLE product_curve_points (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    curve_id    INTEGER NOT NULL REFERENCES product_performance_curves(id),
    x_value     REAL NOT NULL,
    y_value     REAL NOT NULL
);

-- Material compatibility per product
CREATE TABLE product_material_compatibility (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          TEXT NOT NULL REFERENCES products(id),
    fluid_id            TEXT REFERENCES fluids(id),
    fluid_family        TEXT,           -- fallback if specific fluid not in DB
    compatibility_rating TEXT NOT NULL, -- "excellent", "good", "fair", "poor", "incompatible"
    temperature_max_f   REAL,
    source_artifact_id  TEXT REFERENCES knowledge_artifacts(id),
    notes               TEXT
);
```

---

## Layer 6: Consultations

```sql
-- System context: multiple consultations sharing one operating context
CREATE TABLE system_contexts (
    id          TEXT PRIMARY KEY,
    label       TEXT,
    description TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE system_context_consultations (
    system_context_id TEXT NOT NULL REFERENCES system_contexts(id),
    consultation_id   TEXT NOT NULL,
    vertical_id       TEXT NOT NULL REFERENCES verticals(id),
    PRIMARY KEY (system_context_id, consultation_id)
);

-- A consultation: one engineer, one operating context, one primary vertical
CREATE TABLE consultations (
    id                  TEXT PRIMARY KEY,
    operating_context_id TEXT NOT NULL REFERENCES operating_contexts(id),
    system_context_id   TEXT REFERENCES system_contexts(id),
    vertical_id         TEXT NOT NULL REFERENCES verticals(id),
    status              TEXT DEFAULT 'active',   -- "active", "complete", "abandoned"
    created_at          TEXT DEFAULT (datetime('now')),
    completed_at        TEXT
);

-- Full exchange history (for training data and audit)
CREATE TABLE consultation_exchanges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    consultation_id TEXT NOT NULL REFERENCES consultations(id),
    sequence_number INTEGER NOT NULL,
    role            TEXT NOT NULL,     -- "system", "user", "assistant"
    content         TEXT NOT NULL,
    timestamp       TEXT DEFAULT (datetime('now'))
);

-- Recommendations produced by the consultation
CREATE TABLE consultation_recommendations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    consultation_id TEXT NOT NULL REFERENCES consultations(id),
    product_id      TEXT REFERENCES products(id),   -- NULL = spec recommendation, not a specific product
    spec_summary    TEXT,              -- for non-product recommendations
    rank            INTEGER NOT NULL,
    reasoning_chain TEXT NOT NULL,     -- full natural language reasoning — this is the training data
    confidence_score REAL,
    artifacts_cited TEXT,              -- JSON array of artifact_ids used
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Outcome records — populated when engineer reports back
CREATE TABLE consultation_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    consultation_id TEXT NOT NULL REFERENCES consultations(id),
    reported_at     TEXT,
    outcome_data    TEXT NOT NULL,     -- JSON: follows vertical_outcome_templates structure
    notes           TEXT
);

-- Vendor comparison flags extracted during consultations
CREATE TABLE vendor_neutrality_flags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    manufacturer_id TEXT REFERENCES manufacturers(id),
    flag_type       TEXT NOT NULL,     -- "spec-inflation", "test-condition-mismatch", "claim-unverified"
    description     TEXT NOT NULL,
    artifact_id     TEXT REFERENCES knowledge_artifacts(id),
    created_at      TEXT DEFAULT (datetime('now'))
);
```

---

## Layer 7: Active Forum Participation (Gated)

```sql
CREATE TABLE gaps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    gap_type        TEXT NOT NULL,     -- "thin-documentation", "sparse-forum", "vendor-conflict", "no-standard"
    description     TEXT NOT NULL,
    severity        TEXT NOT NULL,     -- "critical", "moderate", "minor"
    parameter_key   TEXT,              -- which vertical parameter has the gap
    fluid_id        TEXT REFERENCES fluids(id),  -- if fluid-specific
    suggested_action TEXT,
    status          TEXT DEFAULT 'open',
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE forum_questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_id          INTEGER NOT NULL REFERENCES gaps(id),
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    target_forum    TEXT NOT NULL,
    target_subforum TEXT,
    question_draft  TEXT NOT NULL,     -- LLM-generated
    question_final  TEXT,              -- human-edited (if changed)
    status          TEXT DEFAULT 'draft',
    approved_by     TEXT,
    approved_at     TEXT,
    posted_at       TEXT,
    thread_url      TEXT,
    thread_id       TEXT,
    reply_count     INTEGER DEFAULT 0,
    last_checked_at TEXT,
    last_reply_at   TEXT,
    follow_up_needed INTEGER DEFAULT 0,
    closed_at       TEXT,
    close_reason    TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE forum_replies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id     INTEGER NOT NULL REFERENCES forum_questions(id),
    reply_author    TEXT,
    reply_date      TEXT,
    reply_text      TEXT NOT NULL,
    author_expertise TEXT,
    ingested        INTEGER DEFAULT 0,
    ingested_at     TEXT,
    artifact_id     TEXT REFERENCES knowledge_artifacts(id),
    created_at      TEXT DEFAULT (datetime('now'))
);
```

---

## Layer 8: Pipeline Operations

```sql
CREATE TABLE pipeline_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id         TEXT NOT NULL REFERENCES verticals(id),
    phase               INTEGER NOT NULL,
    started_at          TEXT NOT NULL,
    completed_at        TEXT,
    status              TEXT DEFAULT 'running',
    artifacts_collected INTEGER DEFAULT 0,
    errors              TEXT,          -- JSON array
    config_snapshot     TEXT           -- JSON of config used
);
```

---

## Cross-Cutting: Tagging Pipeline

When a knowledge artifact is collected, it goes through tagging before being stored:

```
Artifact Collected
       │
       ▼
Rule-Based Pre-tagging
  - artifact_type from URL pattern / content type
  - authority_score from domain heuristics (iso.org = 0.95, eng-tips = 0.7, reddit = 0.5)
       │
       ▼
LLM Tagging (single API call per artifact batch)
  Input: artifact content + vertical ontology (parameter registry)
  Output:
    - vertical_tags (which verticals + relevance score)
    - parameter_tags (which parameters addressed)
    - fluid_tags (which fluids mentioned)
    - authority_score refinement
  Tagging_method = "llm-automated", tagging_model = model version
       │
       ▼
Stored in SQLite (metadata) + Vector Store (content)
```

This tagging call is the primary LLM cost per artifact — small per item, but scales with collection volume. Budget: ~500 input tokens + ~200 output tokens per artifact. At 1000 artifacts per vertical = ~700K tokens per vertical for tagging.

---

## What Changes in the Pipeline Code

The Python collectors remain mostly unchanged — they still fetch, parse, archive, and store. What changes:

1. **`db.py`** — Single `oracle.db` replaces per-vertical databases
2. **New `tagger.py`** — LLM tagging module that runs after each batch of artifacts
3. **`phase1_standards.py`** — Now also populates `fluids` and `fluid_compatibility` from standards text
4. **`phase3_vendors.py`** — Now populates `product_performance_curves` and `product_curve_points`
5. **New `vector_store.py`** — Chroma wrapper for content indexing
6. **`vertical_bootstrap.py`** — Script to register a new vertical and its parameter set before collection begins

The vertical config YAML gains a `parameters` section that bootstraps the `vertical_parameters` table for that vertical.

---

## What to Build First

In order of dependency:

1. **Fluids reference seed data** — a minimal set of common industrial fluids (water, mineral oil, water-glycol, NaOCl 10-15%, diesel) with properties at typical temperatures. This unblocks everything downstream.
2. **Single oracle.db schema** — replace the per-vertical schema
3. **Vertical bootstrap for hydraulic-filters** — register parameters
4. **Revised Phase 1 runner** — collects into new schema, calls tagger
5. **LLM tagger** — batch tagging of artifacts after collection

Then Phase 2-5 builds on a solid foundation.
