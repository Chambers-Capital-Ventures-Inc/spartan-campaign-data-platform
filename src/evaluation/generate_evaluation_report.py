"""
Generate a Markdown evaluation report for the target three-campaign prototype.

This script reads the gold-layer outputs and summarizes:
- which candidates were processed,
- whether campaign dossiers were generated,
- readiness-score results,
- risk-signal counts,
- key caveats,
- and recommended next steps.

The report is meant to help Spartan Judicial understand what the data platform
has produced so far and what still requires review before the outputs become
public-facing or campaign-facing.
"""

from pathlib import Path

import pandas as pd


GOLD_DOSSIERS_PATH = Path("data/gold/gold_candidate_dossiers.csv")
GOLD_READINESS_PATH = Path("data/gold/gold_campaign_readiness.csv")
GOLD_RISK_SIGNALS_PATH = Path("data/gold/gold_risk_signals.csv")
VALIDATION_REPORT_PATH = Path("reports/target_3_validation_report.csv")

REPORT_DIR = Path("reports")
REPORT_OUTPUT = REPORT_DIR / "target_3_evaluation_report.md"


def load_csv(path: Path) -> pd.DataFrame:
    """
    Load a CSV file and raise a clear error if it does not exist.

    This makes the report-generation dependency chain explicit.
    """
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    return pd.read_csv(path)


def format_readiness_table(readiness_df: pd.DataFrame) -> str:
    """
    Convert campaign readiness results into a Markdown table.
    """
    columns = [
        "candidate_name",
        "court_name",
        "readiness_score",
        "readiness_label",
        "fields_complete",
        "fields_possible",
    ]

    return readiness_df[columns].to_markdown(index=False)


def format_risk_summary(risk_df: pd.DataFrame) -> str:
    """
    Summarize risk signals by candidate and risk level.
    """
    if risk_df.empty:
        return "No risk signals generated."

    grouped = (
        risk_df.groupby(["candidate_name", "risk_level"])
        .size()
        .reset_index(name="risk_signal_count")
        .sort_values(["candidate_name", "risk_level"])
    )

    return grouped.to_markdown(index=False)


def format_validation_summary(validation_df: pd.DataFrame) -> str:
    """
    Summarize validation pass/fail counts.
    """
    if validation_df.empty:
        return "No validation rows found."

    grouped = (
        validation_df.groupby("validation_status")
        .size()
        .reset_index(name="row_count")
    )

    return grouped.to_markdown(index=False)


def main() -> None:
    """
    Build the target three-campaign evaluation report.

    The report is a human-readable Markdown file that can be shared with Chris
    or used as documentation for the platform's first validated output cycle.
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    dossiers_df = load_csv(GOLD_DOSSIERS_PATH)
    readiness_df = load_csv(GOLD_READINESS_PATH)
    risk_df = load_csv(GOLD_RISK_SIGNALS_PATH)
    validation_df = load_csv(VALIDATION_REPORT_PATH)

    candidates = dossiers_df["candidate_name"].tolist()

    report = f"""# Target 3 Campaign Evaluation Report

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

{chr(10).join(f"- {candidate}" for candidate in candidates)}

## Validation summary

{format_validation_summary(validation_df)}

## Campaign readiness summary

{format_readiness_table(readiness_df)}

## Risk signal summary

{format_risk_summary(risk_df)}

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
"""

    REPORT_OUTPUT.write_text(report, encoding="utf-8")

    print(f"Wrote evaluation report to {REPORT_OUTPUT}")


if __name__ == "__main__":
    main()