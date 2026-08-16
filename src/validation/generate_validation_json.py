"""
Generate a machine-readable validation report for CI and downstream tooling.

Reads the two validation report CSVs already produced by
src/validation/validate_target_3_dossier.py (row-level silver dossier
validation) and src/validation/validate_gold_outputs.py (gold-layer output
validation), and combines them into a single JSON summary at
reports/validation/validation_report.json.

This gives CI, and any other automation, one small, stable file to check for
pass/fail status instead of parsing two separate CSVs.

Run from the project root:
    python src/validation/generate_validation_json.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

# src/validation/generate_validation_json.py -> repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]

SILVER_VALIDATION_REPORT_PATH = REPO_ROOT / "reports" / "target_3_validation_report.csv"
GOLD_VALIDATION_REPORT_PATH = REPO_ROOT / "reports" / "gold_outputs_validation_report.csv"

VALIDATION_OUTPUT_DIR = REPO_ROOT / "reports" / "validation"
VALIDATION_OUTPUT_PATH = VALIDATION_OUTPUT_DIR / "validation_report.json"

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("generate_validation_json")


def _load_report_records(path: Path) -> list[dict[str, Any]]:
    """Read a validation report CSV and return its rows as plain dicts.

    Empty/NaN cells are converted to None so the result serializes cleanly
    to JSON (bare "NaN" is not valid JSON). This is done per-value rather
    than with DataFrame.where(), because pandas keeps an all-empty column
    as float64 and silently turns an assigned None back into NaN when the
    column dtype is numeric.
    """
    if not path.exists():
        raise FileNotFoundError(f"Validation report not found: {path.relative_to(REPO_ROOT)}")
    df = pd.read_csv(path)
    records = df.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and pd.isna(value):
                record[key] = None
    return records


def summarize_silver_validation(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize the target-three silver dossier row-level validation report.

    Args:
        records: Rows from reports/target_3_validation_report.csv, each with
            row_number, candidate_name, validation_status, and error.
    """
    total_rows = len(records)
    passed_rows = sum(1 for r in records if r.get("validation_status") == "passed")
    failed_rows = total_rows - passed_rows

    return {
        "status": "passed" if failed_rows == 0 and total_rows > 0 else "failed",
        "total_rows": total_rows,
        "passed_rows": passed_rows,
        "failed_rows": failed_rows,
        "records": records,
    }


def summarize_gold_validation(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize the gold-layer output validation report.

    Args:
        records: Rows from reports/gold_outputs_validation_report.csv, each
            with gold_output, path, validation_status, row_count, and
            missing_columns.
    """
    total_outputs = len(records)
    passed_outputs = sum(1 for r in records if r.get("validation_status") == "passed")
    failed_outputs = total_outputs - passed_outputs

    return {
        "status": "passed" if failed_outputs == 0 and total_outputs > 0 else "failed",
        "total_outputs": total_outputs,
        "passed_outputs": passed_outputs,
        "failed_outputs": failed_outputs,
        "records": records,
    }


def collect_failed_checks(
    silver_summary: dict[str, Any], gold_summary: dict[str, Any]
) -> list[str]:
    """Build a flat, human-readable list of every failed check across both reports."""
    failed_checks: list[str] = []

    for record in silver_summary["records"]:
        if record.get("validation_status") != "passed":
            candidate = record.get("candidate_name") or "Unknown candidate"
            error = record.get("error") or "No error message recorded."
            failed_checks.append(f"Silver dossier row failed for {candidate}: {error}")

    for record in gold_summary["records"]:
        if record.get("validation_status") != "passed":
            output_name = record.get("gold_output") or "Unknown gold output"
            missing = record.get("missing_columns") or "Unspecified validation failure."
            failed_checks.append(f"Gold output failed for {output_name}: {missing}")

    return failed_checks


def collect_row_counts(
    silver_summary: dict[str, Any], gold_summary: dict[str, Any]
) -> dict[str, Any]:
    """Build a flat row-count map: silver rows checked plus each gold output's row count."""
    row_counts: dict[str, Any] = {
        "target_3_silver_rows_checked": silver_summary["total_rows"],
    }
    for record in gold_summary["records"]:
        output_name = record.get("gold_output") or "unknown_gold_output"
        row_counts[output_name] = record.get("row_count")
    return row_counts


def build_validation_report(
    silver_path: Path = SILVER_VALIDATION_REPORT_PATH,
    gold_path: Path = GOLD_VALIDATION_REPORT_PATH,
) -> dict[str, Any]:
    """Build the full machine-readable validation report as a plain dict.

    Combines the silver row-level validation report and the gold-layer
    output validation report into one summary with:
        - generated_at: UTC timestamp the report was built.
        - overall_status: "passed" only if every silver row and every gold
          output passed.
        - silver_validation: summary + raw records for the silver report.
        - gold_validation: summary + raw records for the gold report.
        - failed_checks: flat, human-readable list of every failure.
        - row_counts: silver rows checked plus each gold output's row count.
    """
    silver_records = _load_report_records(silver_path)
    gold_records = _load_report_records(gold_path)

    silver_summary = summarize_silver_validation(silver_records)
    gold_summary = summarize_gold_validation(gold_records)

    failed_checks = collect_failed_checks(silver_summary, gold_summary)
    overall_status = "passed" if not failed_checks else "failed"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "silver_validation": silver_summary,
        "gold_validation": gold_summary,
        "failed_checks": failed_checks,
        "row_counts": collect_row_counts(silver_summary, gold_summary),
    }


def write_validation_report(
    report: dict[str, Any], output_path: Path = VALIDATION_OUTPUT_PATH
) -> None:
    """Write the validation report dict to disk as formatted JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    """Generate and write the machine-readable validation report.

    Exits with a non-zero status if the overall validation status is
    "failed", so this script can act as a CI gate.
    """
    logger.info(
        "Reading silver validation report: %s",
        SILVER_VALIDATION_REPORT_PATH.relative_to(REPO_ROOT),
    )
    logger.info(
        "Reading gold validation report: %s",
        GOLD_VALIDATION_REPORT_PATH.relative_to(REPO_ROOT),
    )

    report = build_validation_report()

    write_validation_report(report)
    logger.info("Wrote validation report -> %s", VALIDATION_OUTPUT_PATH.relative_to(REPO_ROOT))
    logger.info("Overall status: %s", report["overall_status"])

    for check in report["failed_checks"]:
        logger.error("Failed check: %s", check)

    if report["overall_status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
