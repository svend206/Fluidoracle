"""
Database layer — single unified oracle.db (SQLite).
All schema creation is idempotent (CREATE TABLE IF NOT EXISTS).
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 3
DB_PATH = Path(__file__).parent.parent / "oracle.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER NOT NULL,
    applied_at TEXT DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------------------
-- Layer 1: Fluid Reference Database
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fluids (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    cas_number      TEXT,
    chemical_family TEXT,
    description     TEXT,
    hazard_class    TEXT,
    fluid_class     TEXT,
    viscosity_grade TEXT,
    trade_names     TEXT,
    base_stock      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fluid_properties (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    fluid_id                TEXT NOT NULL REFERENCES fluids(id),
    concentration_pct       REAL,
    temperature_f           REAL NOT NULL,
    viscosity_dynamic_cp    REAL,
    viscosity_kinematic_cst REAL,
    density_lb_gal          REAL,
    vapor_pressure_psia     REAL,
    ph                      REAL,
    specific_heat_btu_lb_f  REAL,
    bulk_modulus_psi        REAL,
    source                  TEXT,
    confidence              REAL DEFAULT 1.0,
    notes                   TEXT
);
CREATE INDEX IF NOT EXISTS idx_fluid_props
    ON fluid_properties(fluid_id, temperature_f, concentration_pct);

-- Single-value fluid properties not dependent on temperature
-- (pour point, flash point, viscosity index, etc.)
CREATE TABLE IF NOT EXISTS fluid_static_properties (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fluid_id        TEXT NOT NULL REFERENCES fluids(id),
    property_key    TEXT NOT NULL,
    value_numeric   REAL,
    value_text      TEXT,
    unit            TEXT,
    source          TEXT,
    confidence      REAL DEFAULT 1.0,
    notes           TEXT,
    UNIQUE(fluid_id, property_key)
);

-- Viscosity-temperature model coefficients for interpolation
-- Walther (ASTM D341): log log(ν + 0.7) = A - B·log(T_K)
-- Andrade: ln(µ) = A + B/T_K
CREATE TABLE IF NOT EXISTS fluid_viscosity_models (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fluid_id        TEXT NOT NULL REFERENCES fluids(id),
    model_type      TEXT NOT NULL,
    param_a         REAL NOT NULL,
    param_b         REAL NOT NULL,
    param_c         REAL,
    temp_min_f      REAL,
    temp_max_f      REAL,
    r_squared       REAL,
    source          TEXT,
    UNIQUE(fluid_id, model_type)
);

CREATE TABLE IF NOT EXISTS fluid_compatibility (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    fluid_id              TEXT NOT NULL REFERENCES fluids(id),
    concentration_max_pct REAL,
    temperature_max_f     REAL,
    material              TEXT NOT NULL,
    rating                TEXT NOT NULL,
    source_artifact_id    TEXT,
    notes                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_compat ON fluid_compatibility(fluid_id, material);

CREATE TABLE IF NOT EXISTS fluid_static_properties (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    fluid_id            TEXT NOT NULL REFERENCES fluids(id),
    property_key        TEXT NOT NULL,
    value_numeric       REAL,
    value_text          TEXT,
    unit                TEXT,
    source              TEXT,
    confidence          REAL DEFAULT 1.0,
    notes               TEXT,
    UNIQUE(fluid_id, property_key)
);

CREATE TABLE IF NOT EXISTS fluid_viscosity_models (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fluid_id        TEXT NOT NULL REFERENCES fluids(id),
    model_type      TEXT NOT NULL,
    param_a         REAL NOT NULL,
    param_b         REAL NOT NULL,
    param_c         REAL,
    temp_min_f      REAL,
    temp_max_f      REAL,
    r_squared       REAL,
    source          TEXT,
    UNIQUE(fluid_id, model_type)
);

-- -----------------------------------------------------------------------
-- Layer 2: Operating Context
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operating_contexts (
    id         TEXT PRIMARY KEY,
    label      TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS context_fluids (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    context_id              TEXT NOT NULL REFERENCES operating_contexts(id),
    fluid_id                TEXT NOT NULL REFERENCES fluids(id),
    concentration_pct       REAL,
    temperature_f           REAL NOT NULL,
    carries_solids          INTEGER DEFAULT 0,
    solid_type              TEXT,
    solid_loading_mg_l      REAL,
    particle_size_d50_um    REAL,
    particle_size_max_um    REAL,
    resolved_viscosity_cst  REAL,
    resolved_density_lb_gal REAL,
    resolved_ph             REAL,
    properties_resolved_at  TEXT
);

CREATE TABLE IF NOT EXISTS context_system_conditions (
    context_id                TEXT PRIMARY KEY REFERENCES operating_contexts(id),
    flow_rate_gpm             REAL,
    flow_profile              TEXT,
    inlet_pressure_psi        REAL,
    outlet_pressure_psi       REAL,
    differential_pressure_psi REAL,
    pipe_size_inches          REAL,
    pipe_schedule             TEXT,
    ambient_temp_f            REAL,
    installation              TEXT,
    vibration_level           TEXT,
    regulatory                TEXT,
    notes                     TEXT
);

CREATE TABLE IF NOT EXISTS context_requirements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    context_id      TEXT NOT NULL REFERENCES operating_contexts(id),
    vertical_id     TEXT NOT NULL,
    parameter_key   TEXT NOT NULL,
    value_numeric   REAL,
    value_text      TEXT,
    operator        TEXT DEFAULT '>=',
    value_max       REAL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS context_constraints (
    context_id         TEXT PRIMARY KEY REFERENCES operating_contexts(id),
    max_height_in      REAL,
    max_width_in       REAL,
    max_depth_in       REAL,
    approved_materials TEXT,
    excluded_materials TEXT,
    approved_vendors   TEXT,
    excluded_vendors   TEXT,
    budget_usd         REAL,
    weight_limit_lb    REAL,
    integration_notes  TEXT
);

-- -----------------------------------------------------------------------
-- Layer 3: Vertical Ontology
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verticals (
    id           TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description  TEXT,
    active       INTEGER DEFAULT 1,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vertical_parameters (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id           TEXT NOT NULL REFERENCES verticals(id),
    parameter_key         TEXT NOT NULL,
    display_name          TEXT NOT NULL,
    data_type             TEXT NOT NULL,
    unit                  TEXT,
    valid_min             REAL,
    valid_max             REAL,
    allowed_values        TEXT,
    description           TEXT,
    required_for_selection INTEGER DEFAULT 0,
    UNIQUE(vertical_id, parameter_key)
);

CREATE TABLE IF NOT EXISTS vertical_outcome_templates (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id   TEXT NOT NULL REFERENCES verticals(id),
    parameter_key TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    data_type     TEXT NOT NULL,
    description   TEXT,
    UNIQUE(vertical_id, parameter_key)
);

-- -----------------------------------------------------------------------
-- Layer 4: Knowledge Base Index
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_artifacts (
    id                TEXT PRIMARY KEY,
    title             TEXT,
    artifact_type     TEXT NOT NULL,
    source_url        TEXT NOT NULL,
    access_date       TEXT NOT NULL,
    collection_phase  INTEGER,
    collection_method TEXT NOT NULL,
    authority_score   REAL DEFAULT 0.5,
    author            TEXT,
    author_expertise  TEXT,
    publication_date  TEXT,
    raw_snapshot_path TEXT,
    vector_id         TEXT,
    tagging_method    TEXT,
    tagging_model     TEXT,
    created_at        TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON knowledge_artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_url  ON knowledge_artifacts(source_url);

CREATE TABLE IF NOT EXISTS artifact_vertical_tags (
    artifact_id     TEXT NOT NULL REFERENCES knowledge_artifacts(id),
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    relevance_score REAL DEFAULT 1.0,
    tagged_by       TEXT,
    tagged_at       TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (artifact_id, vertical_id)
);

CREATE TABLE IF NOT EXISTS artifact_parameter_tags (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id   TEXT NOT NULL REFERENCES knowledge_artifacts(id),
    vertical_id   TEXT NOT NULL,
    parameter_key TEXT NOT NULL,
    tag_type      TEXT NOT NULL,
    tagged_by     TEXT,
    tagged_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS artifact_fluid_tags (
    artifact_id TEXT NOT NULL REFERENCES knowledge_artifacts(id),
    fluid_id    TEXT NOT NULL REFERENCES fluids(id),
    context     TEXT DEFAULT 'mentioned',
    PRIMARY KEY (artifact_id, fluid_id)
);

CREATE TABLE IF NOT EXISTS standards (
    id              TEXT PRIMARY KEY,
    standard_number TEXT NOT NULL UNIQUE,
    full_title      TEXT,
    issuing_body    TEXT NOT NULL,
    tc_sc           TEXT,
    what_it_governs TEXT,
    current_version TEXT,
    supersedes      TEXT,
    status          TEXT DEFAULT 'active',
    artifact_id     TEXT REFERENCES knowledge_artifacts(id)
);

CREATE TABLE IF NOT EXISTS standard_evidence (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    standard_id        TEXT NOT NULL REFERENCES standards(id),
    artifact_id        TEXT NOT NULL REFERENCES knowledge_artifacts(id),
    mention_type       TEXT NOT NULL,
    context_snippet    TEXT,
    thread_reply_count INTEGER,
    UNIQUE(standard_id, artifact_id, mention_type)
);

CREATE TABLE IF NOT EXISTS standard_relevance (
    standard_id                TEXT NOT NULL REFERENCES standards(id),
    vertical_id                TEXT NOT NULL REFERENCES verticals(id),
    independent_forum_mentions INTEGER DEFAULT 0,
    vendor_catalog_citations   INTEGER DEFAULT 0,
    relevance_tier             TEXT,
    computed_at                TEXT,
    PRIMARY KEY (standard_id, vertical_id)
);

CREATE TABLE IF NOT EXISTS academic_refs (
    id                               TEXT PRIMARY KEY,
    ref_type                         TEXT NOT NULL,
    title                            TEXT NOT NULL,
    authors                          TEXT,
    year                             INTEGER,
    publisher                        TEXT,
    doi                              TEXT,
    isbn                             TEXT,
    practitioner_recommendation_count INTEGER DEFAULT 0,
    topics_covered                   TEXT,
    artifact_id                      TEXT REFERENCES knowledge_artifacts(id)
);

-- -----------------------------------------------------------------------
-- Layer 5: Products
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS manufacturers (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    website          TEXT,
    data_quality     TEXT,
    neutrality_flags TEXT,
    filename_patterns TEXT,
    created_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS products (
    id              TEXT PRIMARY KEY,
    manufacturer_id TEXT NOT NULL REFERENCES manufacturers(id),
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    model_number    TEXT NOT NULL,
    product_line    TEXT,
    display_name    TEXT,
    product_type    TEXT,
    active          INTEGER DEFAULT 1,
    artifact_id     TEXT REFERENCES knowledge_artifacts(id),
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS product_static_specs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id        TEXT NOT NULL REFERENCES products(id),
    parameter_key     TEXT NOT NULL,
    value_numeric     REAL,
    value_text        TEXT,
    unit              TEXT,
    source_artifact_id TEXT REFERENCES knowledge_artifacts(id),
    confidence        REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS product_performance_curves (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id           TEXT NOT NULL REFERENCES products(id),
    curve_type           TEXT NOT NULL,
    x_parameter          TEXT NOT NULL,
    x_unit               TEXT,
    y_parameter          TEXT NOT NULL,
    y_unit               TEXT,
    operating_conditions TEXT,
    source_artifact_id   TEXT REFERENCES knowledge_artifacts(id)
);

CREATE TABLE IF NOT EXISTS product_curve_points (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    curve_id INTEGER NOT NULL REFERENCES product_performance_curves(id),
    x_value  REAL NOT NULL,
    y_value  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS product_material_compatibility (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id           TEXT NOT NULL REFERENCES products(id),
    fluid_id             TEXT REFERENCES fluids(id),
    fluid_family         TEXT,
    compatibility_rating TEXT NOT NULL,
    temperature_max_f    REAL,
    source_artifact_id   TEXT REFERENCES knowledge_artifacts(id),
    notes                TEXT
);

-- -----------------------------------------------------------------------
-- Layer 6: Consultations
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_contexts (
    id          TEXT PRIMARY KEY,
    label       TEXT,
    description TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS system_context_consultations (
    system_context_id TEXT NOT NULL REFERENCES system_contexts(id),
    consultation_id   TEXT NOT NULL,
    vertical_id       TEXT NOT NULL REFERENCES verticals(id),
    PRIMARY KEY (system_context_id, consultation_id)
);

CREATE TABLE IF NOT EXISTS consultations (
    id                   TEXT PRIMARY KEY,
    operating_context_id TEXT NOT NULL REFERENCES operating_contexts(id),
    system_context_id    TEXT REFERENCES system_contexts(id),
    vertical_id          TEXT NOT NULL REFERENCES verticals(id),
    status               TEXT DEFAULT 'active',
    created_at           TEXT DEFAULT (datetime('now')),
    completed_at         TEXT
);

CREATE TABLE IF NOT EXISTS consultation_exchanges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    consultation_id TEXT NOT NULL REFERENCES consultations(id),
    sequence_number INTEGER NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    timestamp       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS consultation_recommendations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    consultation_id TEXT NOT NULL REFERENCES consultations(id),
    product_id      TEXT REFERENCES products(id),
    spec_summary    TEXT,
    rank            INTEGER NOT NULL,
    reasoning_chain TEXT NOT NULL,
    confidence_score REAL,
    artifacts_cited TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS consultation_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    consultation_id TEXT NOT NULL REFERENCES consultations(id),
    reported_at     TEXT,
    outcome_data    TEXT NOT NULL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS vendor_neutrality_flags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    manufacturer_id TEXT REFERENCES manufacturers(id),
    flag_type       TEXT NOT NULL,
    description     TEXT NOT NULL,
    artifact_id     TEXT REFERENCES knowledge_artifacts(id),
    created_at      TEXT DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------------------
-- Layer 7: Active Forum Participation
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gaps (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id      TEXT NOT NULL REFERENCES verticals(id),
    gap_type         TEXT NOT NULL,
    description      TEXT NOT NULL,
    severity         TEXT NOT NULL,
    parameter_key    TEXT,
    fluid_id         TEXT REFERENCES fluids(id),
    suggested_action TEXT,
    status           TEXT DEFAULT 'open',
    created_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS forum_questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    gap_id          INTEGER NOT NULL REFERENCES gaps(id),
    vertical_id     TEXT NOT NULL REFERENCES verticals(id),
    target_forum    TEXT NOT NULL,
    target_subforum TEXT,
    question_draft  TEXT NOT NULL,
    question_final  TEXT,
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

CREATE TABLE IF NOT EXISTS forum_replies (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id      INTEGER NOT NULL REFERENCES forum_questions(id),
    reply_author     TEXT,
    reply_date       TEXT,
    reply_text       TEXT NOT NULL,
    author_expertise TEXT,
    ingested         INTEGER DEFAULT 0,
    ingested_at      TEXT,
    artifact_id      TEXT REFERENCES knowledge_artifacts(id),
    created_at       TEXT DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------------------
-- Layer 8: Pipeline Operations
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    vertical_id         TEXT NOT NULL,
    phase               INTEGER NOT NULL,
    started_at          TEXT NOT NULL,
    completed_at        TEXT,
    status              TEXT DEFAULT 'running',
    artifacts_collected INTEGER DEFAULT 0,
    errors              TEXT,
    config_snapshot     TEXT
);
"""


def init_db() -> None:
    """Create all tables. Idempotent — safe to call on existing DB."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        existing = conn.execute("SELECT version FROM schema_version").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
    print(f"[db] Initialized oracle.db (schema v{SCHEMA_VERSION})")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def save_artifact(
    artifact_id: str,
    title: str,
    artifact_type: str,
    source_url: str,
    access_date: str,
    collection_phase: int,
    collection_method: str,
    authority_score: float = 0.5,
    raw_snapshot_path: Optional[str] = None,
    author: Optional[str] = None,
    author_expertise: Optional[str] = None,
) -> str:
    with get_connection() as conn:
        try:
            conn.execute(
                """INSERT INTO knowledge_artifacts
                   (id, title, artifact_type, source_url, access_date,
                    collection_phase, collection_method, authority_score,
                    raw_snapshot_path, author, author_expertise)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (artifact_id, title, artifact_type, source_url, access_date,
                 collection_phase, collection_method, authority_score,
                 raw_snapshot_path, author, author_expertise),
            )
        except sqlite3.IntegrityError:
            pass  # Idempotent
    return artifact_id


def get_or_create_standard(standard_number: str, **kwargs) -> str:
    std_id = (
        standard_number.upper()
        .replace(" ", "-").replace(":", "-").replace("/", "-")
    )
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM standards WHERE standard_number = ?",
            (standard_number,)
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO standards
                   (id, standard_number, full_title, issuing_body,
                    tc_sc, what_it_governs, current_version, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    std_id, standard_number,
                    kwargs.get("full_title"),
                    kwargs.get("issuing_body", "Unknown"),
                    kwargs.get("tc_sc"),
                    kwargs.get("what_it_governs"),
                    kwargs.get("current_version"),
                    kwargs.get("status", "active"),
                ),
            )
    return std_id


def log_run_start(vertical_id: str, phase: int, config: dict) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO pipeline_runs (vertical_id, phase, started_at, config_snapshot)
               VALUES (?, ?, datetime('now'), ?)""",
            (vertical_id, phase, json.dumps(config)),
        )
        return cursor.lastrowid


def log_run_complete(run_id: int, artifacts: int, errors: list) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE pipeline_runs
               SET completed_at = datetime('now'),
                   status = ?,
                   artifacts_collected = ?,
                   errors = ?
               WHERE id = ?""",
            (
                "failed" if errors else "completed",
                artifacts,
                json.dumps(errors) if errors else None,
                run_id,
            ),
        )
