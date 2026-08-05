-- Mart model: mart_source_quality
--
-- Summarizes the interpretation/context notes in stg_risk_signals by
-- source reference (source_id), so a reviewer can see, per source, how
-- many caveats exist, how severe they are, and how many candidate
-- records reference that source.
--
-- This is a DATA-QUALITY / SOURCE-QUALITY summary. It says nothing about
-- any individual candidate's quality, record, or electability, and it
-- does not rank candidates or sources against each other beyond simple
-- counts of existing recorded notes.

CREATE OR REPLACE VIEW mart_source_quality AS
SELECT
    source_id,
    COUNT(*)                                                    AS total_context_notes,
    COUNT(*) FILTER (WHERE risk_level = 'High')                 AS high_severity_notes,
    COUNT(*) FILTER (WHERE risk_level = 'Medium')                AS medium_severity_notes,
    COUNT(*) FILTER (WHERE risk_level = 'Low')                   AS low_severity_notes,
    COUNT(DISTINCT candidate_name)                               AS candidates_referencing_source,
    STRING_AGG(DISTINCT risk_type, ', ' ORDER BY risk_type)      AS distinct_context_types,
    MAX(run_id)                                                  AS run_id,
    MAX(exported_at)                                             AS exported_at
FROM stg_risk_signals
GROUP BY source_id
ORDER BY source_id;
