-- Mart model: mart_candidate_context
--
-- Joins each interpretation/context note (stg_risk_signals) back to basic
-- candidate identity fields (court name, incumbent status), producing a
-- flat, readable table suited to "important context before interpreting
-- this profile" style displays.
--
-- This model does not rank, compare, or score candidates. It only
-- surfaces the existing, source-scoped interpretation notes alongside
-- enough identity context to display them sensibly per candidate.

CREATE OR REPLACE VIEW mart_candidate_context AS
SELECT
    s.candidate_name,
    d.court_name,
    d.incumbent_status,
    s.risk_type,
    s.risk_level,
    s.risk_message,
    s.source_id,
    s.recommended_action,
    s.run_id,
    s.exported_at
FROM stg_risk_signals s
LEFT JOIN stg_candidate_dossiers d
    ON s.candidate_name = d.candidate_name
ORDER BY s.candidate_name, s.risk_level DESC;
