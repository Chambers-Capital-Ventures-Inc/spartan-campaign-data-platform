-- Staging model: stg_candidate_dossiers
--
-- Source: gold_candidate_dossiers (DuckDB view created by build_duckdb.py
-- over data/lake/gold/gold_candidate_dossiers.parquet).
--
-- Purpose: a light cleaning/typing pass ahead of the mart layer. No
-- scoring, ranking, or comparison across candidates happens here or
-- anywhere downstream in this SQL layer.
--
-- Neutrality notes (carried through unchanged, never dropped):
--   - source_caveat and notes preserve the original source-scope caveats
--     (OCA = court-level context, TEC = report-period totals, SCJC =
--     source-scoped sanctions check, etc.).
--   - filer_id is explicitly cast to VARCHAR so leading zeros survive.

CREATE OR REPLACE VIEW stg_candidate_dossiers AS
SELECT
    candidate_name,
    party,
    court_name,
    court_type,
    incumbent_status,
    bar_status,
    licensed_since,
    public_discipline_flag,
    CAST(filer_id AS VARCHAR)      AS filer_id,          -- preserve leading zeros
    total_contributions,
    total_expenditures,
    oca_case_category,
    active_pending_total,
    long_pending_count,
    long_pending_threshold,
    long_pending_pct,
    scjc_result,
    overall_confidence,
    source_caveat,
    notes,
    run_id,
    exported_at
FROM gold_candidate_dossiers;
