-- Mart model: mart_candidate_profiles
--
-- Combines each candidate's dossier fields (professional background,
-- campaign finance snapshot, court-level context, sanctions check) with
-- the prototype's data-completeness fields, into one candidate-level row.
--
-- Neutrality notes:
--   - data_completeness_score / data_completeness_label measure whether
--     the tracked PROTOTYPE FIELDS are filled. They are not a candidate
--     quality, judicial performance, electability, or voter-persuasion
--     signal, and this model does not rank or compare candidates.
--   - source_caveat and notes are carried through unmodified so that any
--     UI built on this mart cannot silently drop the required
--     interpretation caveats (court-level scope, report-period scope,
--     source-scoped sanctions checks, etc.).
--   - filer_id stays text (via stg_candidate_dossiers) so leading zeros
--     are preserved.

CREATE OR REPLACE VIEW mart_candidate_profiles AS
SELECT
    d.candidate_name,
    d.party,
    d.court_name,
    d.court_type,
    d.incumbent_status,
    d.bar_status,
    d.licensed_since,
    d.public_discipline_flag,
    d.filer_id,
    d.total_contributions,
    d.total_expenditures,
    d.oca_case_category,
    d.active_pending_total,
    d.long_pending_count,
    d.long_pending_threshold,
    d.long_pending_pct,
    d.scjc_result,
    d.overall_confidence,
    d.source_caveat,
    d.notes,
    r.readiness_score              AS data_completeness_score,
    r.readiness_label               AS data_completeness_label,
    r.fields_complete,
    r.fields_possible,
    r.missing_or_review_fields,
    d.run_id,
    d.exported_at
FROM stg_candidate_dossiers d
LEFT JOIN stg_campaign_readiness r
    ON d.candidate_name = r.candidate_name
ORDER BY d.candidate_name;
