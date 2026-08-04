# Target 3 Campaign Evaluation Report

## Summary

The target three-campaign dossier has been cleaned, standardized, and validated.

All three target campaign rows were processed through the first bronze-to-silver-to-gold workflow:

1. Bronze/raw source file
2. Silver cleaned dossier
3. Pydantic schema validation
4. Gold candidate dossier outputs
5. Campaign readiness scoring
6. Data/source risk-signal generation

## Campaigns processed

- Joe Radler
- Paul Sullivan
- Tami Pierce

## Validation summary

| validation_status   |   row_count |
|:--------------------|------------:|
| passed              |           3 |

## Campaign readiness summary

| candidate_name   | court_name           |   readiness_score | readiness_label   |   fields_complete |   fields_possible |
|:-----------------|:---------------------|------------------:|:------------------|------------------:|------------------:|
| Joe Radler       | 311th Family Court   |                 1 | High              |                10 |                10 |
| Paul Sullivan    | 113th Civil Court    |                 1 | High              |                10 |                10 |
| Tami Pierce      | 180th Criminal Court |                 1 | High              |                10 |                10 |

## Risk signal summary

| candidate_name   | risk_level   |   risk_signal_count |
|:-----------------|:-------------|--------------------:|
| Joe Radler       | High         |                   1 |
| Joe Radler       | Low          |                   1 |
| Joe Radler       | Medium       |                   3 |
| Paul Sullivan    | High         |                   1 |
| Paul Sullivan    | Low          |                   1 |
| Paul Sullivan    | Medium       |                   4 |
| Tami Pierce      | Low          |                   1 |
| Tami Pierce      | Medium       |                   5 |

## Outputs generated

- `data/gold/gold_candidate_dossiers.csv`
- `data/gold/gold_campaign_readiness.csv`
- `data/gold/gold_risk_signals.csv`
- `reports/target_3_validation_report.csv`

## Key findings

- The target three-campaign dossier now passes schema validation.
- The platform can produce candidate dossier outputs from cleaned source data.
- The platform can score data readiness without making candidate-quality claims.
- The platform can generate source and interpretation risk signals.
- OCA metrics must remain labeled as court-level context.
- TEC values must remain labeled as report-period totals unless all reports are reconciled.
- SCJC results must remain source-scoped and should not be shortened to “no sanctions.”

## Important caveats

This report evaluates data readiness, not candidate quality or election competitiveness.

Readiness scores indicate how complete and usable the structured data is. They do not indicate whether a candidate is good, bad, likely to win, or preferable to another candidate.

Risk signals are data/source warnings. They are intended to help Spartan Judicial avoid unsupported claims and preserve careful wording.

## Recommended next steps

1. Review direct source links for State Bar, TEC, OCA, and SCJC records.
2. Add direct TEC report URLs where available.
3. Confirm fiscal years checked for SCJC searches.
4. Expand the same bronze/silver/gold pattern to the broader candidate roster.
5. Use these gold files as the input layer for the first Streamlit dashboard.
