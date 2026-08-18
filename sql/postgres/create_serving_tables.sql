-- Serving-layer schema for the Spartan Judicial Candidate Lookup app.
--
-- These tables are the eventual Postgres/Supabase read target for the
-- frontend. They are populated by src/storage/export_to_postgres.py from
-- the DuckDB marts (sql/marts/*.sql) when available, or from the
-- data/gold/*.csv files as a fallback. This file only defines the schema;
-- it never has to be run manually before using the export script, which
-- applies it automatically (every statement is idempotent).
--
-- Neutrality notes (apply to every table below, not just candidate_profiles):
--   - Nothing here ranks, scores, or compares candidates against each
--     other. "Completeness" fields describe how much of the tracked
--     PROTOTYPE data is filled in, not candidate quality or electability.
--   - source_caveat, notes, and candidate_context_notes rows must be
--     preserved and displayed alongside any value they qualify (OCA =
--     court-level context, TEC = report-period totals, SCJC =
--     source-scoped sanctions check, etc.).
--
-- Safe to re-run: every statement uses IF NOT EXISTS, so applying this
-- file against a database that already has these tables is a no-op.

-- 1. candidate_profiles
-- Core public-record dossier fields for one candidate. filer_id is TEXT
-- (not INTEGER/NUMERIC) so leading zeros in TEC filer IDs are preserved.
CREATE TABLE IF NOT EXISTS candidate_profiles (
    candidate_name          TEXT PRIMARY KEY,
    party                   TEXT,
    court_name              TEXT,
    court_type              TEXT,
    incumbent_status        TEXT,
    bar_status              TEXT,
    licensed_since          TEXT,
    public_discipline_flag  TEXT,
    filer_id                TEXT,               -- kept as text: preserves leading zeros
    total_contributions     NUMERIC,
    total_expenditures      NUMERIC,
    oca_case_category       TEXT,
    active_pending_total    INTEGER,
    long_pending_count      INTEGER,
    long_pending_threshold  TEXT,
    long_pending_pct        DOUBLE PRECISION,
    scjc_result             TEXT,
    overall_confidence      TEXT,
    source_caveat           TEXT,
    notes                   TEXT,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. candidate_profile_completeness
-- Data-completeness metrics for the tracked prototype fields. This is a
-- DATA-QUALITY signal, not a candidate-quality or electability signal.
CREATE TABLE IF NOT EXISTS candidate_profile_completeness (
    candidate_name             TEXT PRIMARY KEY REFERENCES candidate_profiles (candidate_name),
    court_name                 TEXT,
    incumbent_status           TEXT,
    readiness_score            DOUBLE PRECISION,   -- completeness score (0-1), not a quality score
    readiness_label            TEXT,               -- completeness label, not a quality label
    fields_complete            INTEGER,
    fields_possible            INTEGER,
    missing_or_review_fields   TEXT,
    overall_confidence         TEXT,
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. candidate_context_notes
-- Interpretation/context notes for a candidate's profile (sourced from the
-- gold risk-signal table). These describe how to correctly READ the data
-- above, not a judgment about the candidate. One row per
-- (candidate_name, risk_type); upserts key off that pair since there is no
-- natural single-column identifier in the source data.
CREATE TABLE IF NOT EXISTS candidate_context_notes (
    id                   BIGSERIAL PRIMARY KEY,
    candidate_name       TEXT NOT NULL REFERENCES candidate_profiles (candidate_name),
    risk_type            TEXT NOT NULL,
    risk_level           TEXT,
    risk_message         TEXT,
    source_id            TEXT,               -- kept as text: source references are alphanumeric codes
    recommended_action   TEXT,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_candidate_context_notes_candidate_risk_type UNIQUE (candidate_name, risk_type)
);

-- 4. source_quality
-- Per-source rollup of how many context notes exist and how severe they
-- are. A DATA-QUALITY summary of the sources feeding the prototype, not a
-- statement about any individual candidate.
CREATE TABLE IF NOT EXISTS source_quality (
    source_id                        TEXT PRIMARY KEY,
    total_context_notes              INTEGER,
    high_severity_notes              INTEGER,
    medium_severity_notes            INTEGER,
    low_severity_notes               INTEGER,
    candidates_referencing_source    INTEGER,
    distinct_context_types           TEXT,
    updated_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. pipeline_runs
-- One row per pipeline execution (from reports/pipeline_runs/*.txt),
-- so the frontend/ops can see when data was last refreshed and whether
-- the last run passed.
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id           TEXT PRIMARY KEY,
    status           TEXT NOT NULL,
    timestamp_utc    TIMESTAMPTZ,
    error            TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 6. semantic_candidate_summaries
-- Pre-generated, plain-English narrative text per candidate, built by
-- deterministic template functions (see export_to_postgres.py) — not an
-- LLM. Lets the frontend render readable copy without recomputing
-- sentence templates on every page load.
CREATE TABLE IF NOT EXISTS semantic_candidate_summaries (
    candidate_name           TEXT PRIMARY KEY REFERENCES candidate_profiles (candidate_name),
    profile_summary          TEXT,
    finance_summary          TEXT,
    court_context_summary    TEXT,
    generated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
