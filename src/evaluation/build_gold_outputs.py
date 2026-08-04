"""
Build gold-layer outputs for the Spartan Judicial campaign data platform.

This script reads the cleaned silver target-campaign dossier and produces
campaign-ready gold outputs:

1. gold_candidate_dossiers.csv
   A simplified candidate dossier table designed for dashboard/profile use.

2. gold_campaign_readiness.csv
   A data-readiness scoring table that evaluates how complete and usable each
   candidate dossier is.

3. gold_risk_signals.csv
   A source/data-risk signal table that flags caveats, missing fields, and
   interpretation risks. These are data-readiness risks, not candidate-quality
   judgments.

The goal is to move from cleaned data to product-ready outputs that Spartan
Judicial can use for candidate profiles, campaign readiness review, and source
verification workflows.
"""

from pathlib import Path
from typing import Any

import pandas as pd


SILVER_INPUT = Path("data/silver/target_3_campaign_dossier_clean.csv")
GOLD_DIR = Path("data/gold")

GOLD_DOSSIERS_OUTPUT = GOLD_DIR / "gold_candidate_dossiers.csv"
GOLD_READINESS_OUTPUT = GOLD_DIR / "gold_campaign_readiness.csv"
GOLD_RISK_SIGNALS_OUTPUT = GOLD_DIR / "gold_risk_signals.csv"


GOLD_DOSSIER_COLUMNS = [
    "candidate_name",
    "party",
    "court_name",
    "court_type",
    "incumbent_status",
    "bar_status",
    "licensed_since",
    "public_discipline_flag",
    "filer_id",
    "total_contributions",
    "total_expenditures",
    "oca_case_category",
    "active_pending_total",
    "long_pending_count",
    "long_pending_threshold",
    "long_pending_pct",
    "scjc_result",
    "overall_confidence",
    "source_caveat",
    "notes",
]


READINESS_FIELDS = [
    "state_bar_profile_url",
    "bar_number",
    "public_discipline_flag",
    "filer_id",
    "total_contributions",
    "total_expenditures",
    "active_pending_total",
    "long_pending_pct",
    "scjc_checked",
    "overall_confidence",
]


def is_filled(value: Any) -> bool:
    """
    Return True if a field contains usable data.

    This treats nulls, empty strings, and common unresolved status values as not
    filled. The purpose is to support readiness scoring without pretending that
    placeholders like "Not checked" are complete data.
    """
    if pd.isna(value):
        return False

    value_str = str(value).strip()

    if value_str == "":
        return False

    unresolved_values = {
        "Not checked",
        "Unknown",
        "Needs verification",
        "No clear match found",
        "Not found",
        "None",
        "nan",
    }

    return value_str not in unresolved_values


def readiness_label(score: float) -> str:
    """
    Convert a numeric readiness score into a simple label.

    This score measures data readiness, not candidate quality.
    """
    if score >= 0.8:
        return "High"
    if score >= 0.5:
        return "Medium"
    return "Low"


def build_gold_candidate_dossiers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build the campaign-ready candidate dossier table.

    This gold table keeps only the fields most useful for candidate profile
    views. It excludes lower-level ingestion fields while preserving key
    caveats and notes needed for responsible interpretation.
    """
    missing_cols = [col for col in GOLD_DOSSIER_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required gold dossier columns: {missing_cols}")

    return df[GOLD_DOSSIER_COLUMNS].copy()


def build_campaign_readiness(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a campaign readiness table for each candidate.

    The readiness score answers:
    "How complete and usable is this candidate's data record right now?"

    It does not answer:
    "How good is this candidate?"
    "How strong is this campaign?"
    "Who should voters support?"

    The score is based on whether key fields are populated and verified enough
    to support a prototype dossier.
    """
    rows = []

    for _, row in df.iterrows():
        complete_fields = []
        missing_fields = []

        for field in READINESS_FIELDS:
            if field not in df.columns:
                missing_fields.append(field)
                continue

            if is_filled(row[field]):
                complete_fields.append(field)
            else:
                missing_fields.append(field)

        fields_complete = len(complete_fields)
        fields_possible = len(READINESS_FIELDS)
        score = fields_complete / fields_possible if fields_possible else 0.0

        rows.append(
            {
                "candidate_name": row["candidate_name"],
                "court_name": row["court_name"],
                "incumbent_status": row["incumbent_status"],
                "readiness_score": round(score, 3),
                "readiness_label": readiness_label(score),
                "fields_complete": fields_complete,
                "fields_possible": fields_possible,
                "missing_or_review_fields": "; ".join(missing_fields)
                if missing_fields
                else "None",
                "overall_confidence": row.get("overall_confidence", "Unknown"),
            }
        )

    return pd.DataFrame(rows)


def build_risk_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build source/data-readiness risk signals for each candidate.

    These signals are not accusations and are not candidate-quality judgments.
    They are warnings about interpretation, source limitations, missing fields,
    or manual verification needs.

    Example:
    OCA backlog metrics should be shown as court-level context, not as direct
    proof of individual candidate performance.
    """
    signals = []

    for _, row in df.iterrows():
        candidate_name = row["candidate_name"]
        incumbent_status = row.get("incumbent_status", "Unknown")
        long_pending_pct = row.get("long_pending_pct")

        # Universal OCA caveat.
        signals.append(
            {
                "candidate_name": candidate_name,
                "risk_type": "court_metric_interpretation",
                "risk_level": "Medium",
                "risk_message": (
                    "OCA metrics are court-level context for the seat, not "
                    "individual candidate performance."
                ),
                "source_id": "SRC002",
                "recommended_action": (
                    "Preserve court-level caveat anywhere OCA metrics appear."
                ),
            }
        )

        # Challenger-specific caveat.
        if incumbent_status == "Challenger":
            signals.append(
                {
                    "candidate_name": candidate_name,
                    "risk_type": "challenger_interpretation",
                    "risk_level": "High",
                    "risk_message": (
                        "Candidate is a challenger, so current court metrics "
                        "should not be framed as the candidate's personal record."
                    ),
                    "source_id": "SRC002",
                    "recommended_action": (
                        "Use wording: court-level context for the seat this "
                        "candidate is running for."
                    ),
                }
            )

        # Incumbent-specific caveat.
        if incumbent_status == "Incumbent":
            signals.append(
                {
                    "candidate_name": candidate_name,
                    "risk_type": "incumbent_interpretation",
                    "risk_level": "Medium",
                    "risk_message": (
                        "Candidate is an incumbent, but court-level metrics may "
                        "still reflect staffing, filings, case mix, and broader "
                        "court-system conditions."
                    ),
                    "source_id": "SRC002",
                    "recommended_action": (
                        "Avoid framing OCA metrics as sole proof of individual "
                        "responsibility."
                    ),
                }
            )

        # TEC caveat.
        signals.append(
            {
                "candidate_name": candidate_name,
                "risk_type": "campaign_finance_scope",
                "risk_level": "Medium",
                "risk_message": (
                    "TEC contribution and expenditure values are latest "
                    "report-period totals, not lifetime or full-cycle totals."
                ),
                "source_id": "SRC005",
                "recommended_action": (
                    "Display report-period caveat near campaign finance values."
                ),
            }
        )

        # SCJC caveat.
        signals.append(
            {
                "candidate_name": candidate_name,
                "risk_type": "scjc_scope",
                "risk_level": "Medium",
                "risk_message": (
                    "SCJC result is source-scoped. No matching public sanction "
                    "found in checked pages does not mean no sanctions ever."
                ),
                "source_id": "SRC006",
                "recommended_action": (
                    "Use source-scoped wording for sanctions checks."
                ),
            }
        )

        # Missing direct source link caveat.
        if "Simple Search Results page" in str(row.get("campaign_finance_url", "")):
            signals.append(
                {
                    "candidate_name": candidate_name,
                    "risk_type": "source_link_specificity",
                    "risk_level": "Low",
                    "risk_message": (
                        "Campaign finance URL is a source description/search "
                        "page rather than a direct report URL."
                    ),
                    "source_id": "SRC005",
                    "recommended_action": (
                        "Add direct TEC filer/report URL when available."
                    ),
                }
            )

        # High long-pending context signal.
        if pd.notna(long_pending_pct) and float(long_pending_pct) >= 0.15:
            signals.append(
                {
                    "candidate_name": candidate_name,
                    "risk_type": "high_long_pending_context",
                    "risk_level": "Medium",
                    "risk_message": (
                        f"Long-pending court context is relatively high "
                        f"({float(long_pending_pct):.1%}). This requires careful "
                        f"court-level interpretation."
                    ),
                    "source_id": "SRC002",
                    "recommended_action": (
                        "If shown in dashboard, explain threshold and court-level scope."
                    ),
                }
            )

    return pd.DataFrame(signals)


def main() -> None:
    """
    Run the full gold-output build process.

    Reads the cleaned target-campaign dossier from the silver layer and writes
    three gold outputs:
    - candidate dossiers
    - campaign readiness scores
    - data/source risk signals
    """
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(
        SILVER_INPUT,
        dtype={
            "bar_number": str,
            "filer_id": str,
        },
    )

    gold_dossiers = build_gold_candidate_dossiers(df)
    readiness = build_campaign_readiness(df)
    risk_signals = build_risk_signals(df)

    gold_dossiers.to_csv(GOLD_DOSSIERS_OUTPUT, index=False)
    readiness.to_csv(GOLD_READINESS_OUTPUT, index=False)
    risk_signals.to_csv(GOLD_RISK_SIGNALS_OUTPUT, index=False)

    print(f"Wrote {GOLD_DOSSIERS_OUTPUT}")
    print(f"Wrote {GOLD_READINESS_OUTPUT}")
    print(f"Wrote {GOLD_RISK_SIGNALS_OUTPUT}")


if __name__ == "__main__":
    main()