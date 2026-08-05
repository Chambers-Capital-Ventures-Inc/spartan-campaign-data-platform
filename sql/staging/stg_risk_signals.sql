-- Staging model: stg_risk_signals
--
-- Source: gold_risk_signals (DuckDB view created by build_duckdb.py over
-- data/lake/gold/gold_risk_signals.parquet).
--
-- Purpose: a light cleaning/typing pass ahead of the mart layer. These
-- rows are interpretation/context notes (e.g. "OCA metrics are
-- court-level context, not individual candidate performance") — they
-- describe how to correctly READ the data, not a judgment about any
-- candidate.
--
-- source_id is explicitly cast to VARCHAR so identifier formatting is
-- preserved consistently with filer_id/bar_number elsewhere.

CREATE OR REPLACE VIEW stg_risk_signals AS
SELECT
    candidate_name,
    risk_type,
    risk_level,                         -- High / Medium / Low severity of the note
    risk_message,
    CAST(source_id AS VARCHAR)     AS source_id,
    recommended_action,
    run_id,
    exported_at
FROM gold_risk_signals;
