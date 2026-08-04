"""
Validate gold-layer output files for the Spartan Judicial data platform.

This script checks whether the expected gold CSV files exist and whether each
contains the required columns.

This is not row-level Pydantic validation. Instead, it is a lightweight
data-product validation step that confirms the gold layer has the structure
expected by downstream reports and dashboards.
"""

from pathlib import Path

import pandas as pd


REPORT_DIR = Path("reports")
REPORT_OUTPUT = REPORT_DIR / "gold_outputs_validation_report.csv"


GOLD_FILES = {
    "gold_candidate_dossiers": {
        "path": Path("data/gold/gold_candidate_dossiers.csv"),
        "required_columns": [
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
        ],
    },
    "gold_campaign_readiness": {
        "path": Path("data/gold/gold_campaign_readiness.csv"),
        "required_columns": [
            "candidate_name",
            "court_name",
            "incumbent_status",
            "readiness_score",
            "readiness_label",
            "fields_complete",
            "fields_possible",
            "missing_or_review_fields",
            "overall_confidence",
        ],
    },
    "gold_risk_signals": {
        "path": Path("data/gold/gold_risk_signals.csv"),
        "required_columns": [
            "candidate_name",
            "risk_type",
            "risk_level",
            "risk_message",
            "source_id",
            "recommended_action",
        ],
    },
}


def validate_file(name: str, path: Path, required_columns: list[str]) -> dict:
    """
    Validate one gold-layer CSV file.

    Returns a dictionary summarizing whether the file exists, whether required
    columns are present, and how many rows it contains.
    """
    if not path.exists():
        return {
            "gold_output": name,
            "path": str(path),
            "validation_status": "failed",
            "row_count": 0,
            "missing_columns": "FILE_NOT_FOUND",
        }

    df = pd.read_csv(path)
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        status = "failed"
    else:
        status = "passed"

    return {
        "gold_output": name,
        "path": str(path),
        "validation_status": status,
        "row_count": len(df),
        "missing_columns": "; ".join(missing_columns) if missing_columns else "",
    }


def main() -> None:
    """
    Run validation checks across all expected gold-layer outputs.
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    results = []

    for name, config in GOLD_FILES.items():
        results.append(
            validate_file(
                name=name,
                path=config["path"],
                required_columns=config["required_columns"],
            )
        )

    report_df = pd.DataFrame(results)
    report_df.to_csv(REPORT_OUTPUT, index=False)

    print(f"Wrote gold output validation report to {REPORT_OUTPUT}")
    print(report_df)


if __name__ == "__main__":
    main()