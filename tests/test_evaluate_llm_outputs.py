import json

import pandas as pd
import pytest

from src.llm import evaluate_llm_outputs as evl
from src.llm.generate_candidate_explanations import (
    COURT_LEVEL_CAVEAT,
    REPORT_PERIOD_CAVEAT,
    SOURCE_SCOPED_CAVEAT,
)


# ---------------------------------------------------------------------------
# find_banned_phrases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Please vote for this candidate in November.",
        "This is the best candidate in the race.",
        "Analysts say she will win the election.",
        "The filings suggest he is corrupt.",
        "This candidate is unfit for office.",
        "Overall this is a strong candidate compared to others.",
        "We endorse this candidate for judge.",
    ],
)
def test_find_banned_phrases_detects_violations(text):
    assert evl.find_banned_phrases(text) != []


def test_find_banned_phrases_clean_text_has_no_hits():
    text = (
        "TEC filer records show total contributions of $2,500.00 and total "
        "expenditures of $0.00. TEC contribution and expenditure values are "
        "latest available report-period totals, not lifetime or full-cycle "
        "totals."
    )
    assert evl.find_banned_phrases(text) == []


def test_find_banned_phrases_handles_non_string():
    assert evl.find_banned_phrases(None) == []
    assert evl.find_banned_phrases(float("nan")) == []


def test_find_banned_phrases_does_not_flag_neutral_criminal_court_name():
    # Regression test: several real court names/types in this dataset are
    # legitimately "Criminal Court" / "Criminal District Court" — a neutral
    # jurisdiction label, not an accusation against the candidate.
    text = (
        "Tami Pierce is listed in this prototype as a Democratic candidate "
        "for the 180th Criminal Court, running as a(n) incumbent."
    )
    assert evl.find_banned_phrases(text) == []


def test_find_banned_phrases_flags_actual_accusatory_criminal_language():
    assert evl.find_banned_phrases("Records show a criminal record for this candidate.") != []
    assert evl.find_banned_phrases("This candidate was convicted of a crime.") != []


# ---------------------------------------------------------------------------
# find_missing_required_caveats
# ---------------------------------------------------------------------------


def test_finance_explanation_requires_report_period_caveat():
    missing = evl.find_missing_required_caveats("finance_explanation", "No caveat here at all.")
    assert missing == [REPORT_PERIOD_CAVEAT]


def test_finance_explanation_passes_when_caveat_present():
    text = f"Some finance text. {REPORT_PERIOD_CAVEAT}"
    assert evl.find_missing_required_caveats("finance_explanation", text) == []


def test_court_context_requires_court_level_caveat():
    missing = evl.find_missing_required_caveats("court_context_explanation", "No caveat here.")
    assert missing == [COURT_LEVEL_CAVEAT]


def test_court_context_passes_when_caveat_present():
    text = f"Court numbers here. {COURT_LEVEL_CAVEAT}"
    assert evl.find_missing_required_caveats("court_context_explanation", text) == []


def test_public_record_notes_requires_source_scoped_caveat():
    missing = evl.find_missing_required_caveats("public_record_notes_explanation", "No caveat here.")
    assert missing == [SOURCE_SCOPED_CAVEAT]


def test_public_record_notes_passes_when_caveat_present():
    text = f"SCJC result text. {SOURCE_SCOPED_CAVEAT}"
    assert evl.find_missing_required_caveats("public_record_notes_explanation", text) == []


@pytest.mark.parametrize("summary_type", ["candidate_overview", "professional_background"])
def test_summary_types_without_required_caveats_never_flag_missing(summary_type):
    assert evl.find_missing_required_caveats(summary_type, "Any text at all.") == []


# ---------------------------------------------------------------------------
# evaluate_row / RowEvaluation
# ---------------------------------------------------------------------------


def test_evaluate_row_passes_for_compliant_finance_text():
    text = f"Total contributions were $100.00. {REPORT_PERIOD_CAVEAT}"
    result = evl.evaluate_row("Jane Doe", "finance_explanation", text, run_id="run_test")
    assert result.passed is True
    assert result.banned_phrases_found == []
    assert result.missing_required_caveats == []


def test_evaluate_row_fails_for_missing_caveat_and_banned_phrase():
    text = "This is the best candidate and will win easily."
    result = evl.evaluate_row("Jane Doe", "finance_explanation", text)
    assert result.passed is False
    assert result.missing_required_caveats == [REPORT_PERIOD_CAVEAT]
    assert set(result.banned_phrases_found) >= {"best candidate", "will win"}


# ---------------------------------------------------------------------------
# build_report / evaluate_records
# ---------------------------------------------------------------------------


def test_build_report_shape():
    records = [
        {
            "candidate_name": "Jane Doe",
            "summary_type": "finance_explanation",
            "generated_text": f"Some text. {REPORT_PERIOD_CAVEAT}",
            "run_id": "run_test",
        },
        {
            "candidate_name": "Jane Doe",
            "summary_type": "finance_explanation",
            "generated_text": "No caveat and vote for her.",
            "run_id": "run_test",
        },
    ]
    evaluations = evl.evaluate_records(records)
    report_df = evl.build_report(evaluations)
    assert list(report_df.columns) == [
        "candidate_name",
        "summary_type",
        "run_id",
        "passed",
        "banned_phrases_found",
        "missing_required_caveats",
    ]
    assert report_df["passed"].tolist() == [True, False]


# ---------------------------------------------------------------------------
# load_records
# ---------------------------------------------------------------------------


def test_load_records_jsonl(tmp_path):
    path = tmp_path / "summaries.jsonl"
    rows = [
        {"candidate_name": "A", "summary_type": "candidate_overview", "generated_text": "Hi"},
        {"candidate_name": "B", "summary_type": "candidate_overview", "generated_text": "Hello"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    loaded = evl.load_records(path)
    assert loaded == rows


def test_load_records_csv(tmp_path):
    path = tmp_path / "summaries.csv"
    pd.DataFrame(
        [{"candidate_name": "A", "summary_type": "candidate_overview", "generated_text": "Hi"}]
    ).to_csv(path, index=False)
    loaded = evl.load_records(path)
    assert loaded[0]["candidate_name"] == "A"


def test_load_records_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "summaries.txt"
    path.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError):
        evl.load_records(path)


# ---------------------------------------------------------------------------
# main() end-to-end against a temp file
# ---------------------------------------------------------------------------


def test_main_returns_nonzero_when_any_row_fails(tmp_path, monkeypatch):
    input_path = tmp_path / "summaries.jsonl"
    rows = [
        {
            "candidate_name": "Jane Doe",
            "summary_type": "finance_explanation",
            "generated_text": f"Fine. {REPORT_PERIOD_CAVEAT}",
            "run_id": "run_test",
        },
        {
            "candidate_name": "Jane Doe",
            "summary_type": "court_context_explanation",
            "generated_text": "Missing the caveat and says vote for her.",
            "run_id": "run_test",
        },
    ]
    input_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    report_dir = tmp_path / "reports"
    monkeypatch.setattr(evl, "REPORT_DIR", report_dir)
    monkeypatch.setattr(evl, "REPORT_OUTPUT", report_dir / "llm_output_evaluation_report.csv")
    monkeypatch.setattr("sys.argv", ["evaluate_llm_outputs.py", "--input", str(input_path)])

    exit_code = evl.main()
    assert exit_code == 1
    assert (report_dir / "llm_output_evaluation_report.csv").exists()


def test_main_returns_zero_when_all_rows_pass(tmp_path, monkeypatch):
    input_path = tmp_path / "summaries.jsonl"
    rows = [
        {
            "candidate_name": "Jane Doe",
            "summary_type": "public_record_notes_explanation",
            "generated_text": f"No matching sanction found. {SOURCE_SCOPED_CAVEAT}",
            "run_id": "run_test",
        },
    ]
    input_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    report_dir = tmp_path / "reports"
    monkeypatch.setattr(evl, "REPORT_DIR", report_dir)
    monkeypatch.setattr(evl, "REPORT_OUTPUT", report_dir / "llm_output_evaluation_report.csv")
    monkeypatch.setattr("sys.argv", ["evaluate_llm_outputs.py", "--input", str(input_path)])

    exit_code = evl.main()
    assert exit_code == 0
