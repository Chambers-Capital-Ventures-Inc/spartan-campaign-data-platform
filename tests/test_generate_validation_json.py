"""
Tests for src/validation/generate_validation_json.py.

These tests are fully local and deterministic: they read the validation
report CSVs already checked into the repo (reports/target_3_validation_report.csv
and reports/gold_outputs_validation_report.csv) and exercise the report
builder as a pure function. No network access, database, or LLM API key is
required.

Run from the project root:
    python -m pytest
"""

from pathlib import Path

from src.validation.generate_validation_json import (
    build_validation_report,
    collect_failed_checks,
    summarize_gold_validation,
    summarize_silver_validation,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SILVER_REPORT_PATH = REPO_ROOT / "reports" / "target_3_validation_report.csv"
GOLD_REPORT_PATH = REPO_ROOT / "reports" / "gold_outputs_validation_report.csv"


def test_build_validation_report_has_required_keys():
    """The report must include every key CI/downstream tooling depends on."""
    report = build_validation_report(SILVER_REPORT_PATH, GOLD_REPORT_PATH)

    for key in (
        "generated_at",
        "overall_status",
        "silver_validation",
        "gold_validation",
        "failed_checks",
        "row_counts",
    ):
        assert key in report


def test_build_validation_report_passes_on_checked_in_reports():
    """The checked-in report CSVs currently show all checks passing."""
    report = build_validation_report(SILVER_REPORT_PATH, GOLD_REPORT_PATH)

    assert report["overall_status"] == "passed"
    assert report["failed_checks"] == []


def test_row_counts_include_each_gold_output():
    """row_counts should expose the silver rows checked plus each gold output's row count."""
    report = build_validation_report(SILVER_REPORT_PATH, GOLD_REPORT_PATH)
    row_counts = report["row_counts"]

    assert row_counts["target_3_silver_rows_checked"] == 3
    assert row_counts["gold_candidate_dossiers"] == 3
    assert row_counts["gold_campaign_readiness"] == 3
    assert row_counts["gold_risk_signals"] == 17


def test_summarize_silver_validation_flags_failures():
    """A failed row should flip the silver summary status and counts."""
    records = [
        {"row_number": 1, "candidate_name": "A", "validation_status": "passed", "error": None},
        {"row_number": 2, "candidate_name": "B", "validation_status": "failed", "error": "bad data"},
    ]

    summary = summarize_silver_validation(records)

    assert summary["status"] == "failed"
    assert summary["total_rows"] == 2
    assert summary["passed_rows"] == 1
    assert summary["failed_rows"] == 1


def test_summarize_gold_validation_all_passed():
    """When every gold output passes, the gold summary status should be 'passed'."""
    records = [
        {"gold_output": "gold_x", "validation_status": "passed", "row_count": 3, "missing_columns": None},
    ]

    summary = summarize_gold_validation(records)

    assert summary["status"] == "passed"
    assert summary["failed_outputs"] == 0


def test_collect_failed_checks_reports_gold_failures():
    """A failed gold output should produce a readable failed_checks entry naming it."""
    silver_summary = {"records": []}
    gold_summary = {
        "records": [
            {"gold_output": "gold_x", "validation_status": "failed", "missing_columns": "foo"},
        ]
    }

    failed = collect_failed_checks(silver_summary, gold_summary)

    assert len(failed) == 1
    assert "gold_x" in failed[0]
