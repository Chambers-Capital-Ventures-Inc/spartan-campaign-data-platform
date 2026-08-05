-- Staging model: stg_campaign_readiness
--
-- Source: gold_campaign_readiness (DuckDB view created by build_duckdb.py
-- over data/lake/gold/gold_campaign_readiness.parquet).
--
-- Purpose: a light cleaning/typing pass ahead of the mart layer.
--
-- Neutrality note: readiness_score / readiness_label describe the
-- completeness of the tracked PROTOTYPE FIELDS for a candidate record.
-- They are a data-completeness signal, not a measure of candidate
-- quality, judicial performance, electability, or voter support, and
-- they are never used to rank candidates against one another.

CREATE OR REPLACE VIEW stg_campaign_readiness AS
SELECT
    candidate_name,
    court_name,
    incumbent_status,
    readiness_score,               -- data-completeness score (0-1), not a quality score
    readiness_label,                -- data-completeness label, not a quality label
    fields_complete,
    fields_possible,
    missing_or_review_fields,
    overall_confidence,
    run_id,
    exported_at
FROM gold_campaign_readiness;
