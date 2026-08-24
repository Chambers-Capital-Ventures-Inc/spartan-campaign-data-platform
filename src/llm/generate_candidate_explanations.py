"""
Generate source-grounded, plain-English candidate explanations.

Architecture rule this file exists to enforce: the LLM (or, in mock mode,
the deterministic template stand-in for it) runs strictly AFTER the gold
layer has been built and validated. This script only reads already-validated
facts from data/gold/*.csv and asks a model to phrase them for a
non-technical reader. It never invents facts, never decides what the
underlying data is, and never scores, ranks, or makes a quality judgment
about a candidate. See docs/llm_explanation_layer.md for the full design.

Two run modes, selected by SPARTAN_LLM_MODE (env var) or --mode:

- mock (default): deterministic string templates, no network call, no API
  key required. This is what tests and CI use.
- live: calls the Anthropic Messages API. Requires ANTHROPIC_API_KEY and the
  `anthropic` package. Never required for tests.

Run from the project root:
    python src/llm/generate_candidate_explanations.py
    SPARTAN_LLM_MODE=live python src/llm/generate_candidate_explanations.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

DATA_GOLD = REPO_ROOT / "data" / "gold"
GOLD_DOSSIERS = DATA_GOLD / "gold_candidate_dossiers.csv"
GOLD_READINESS = DATA_GOLD / "gold_campaign_readiness.csv"
GOLD_RISK_SIGNALS = DATA_GOLD / "gold_risk_signals.csv"

LAKE_SEMANTIC_DIR = REPO_ROOT / "data" / "lake" / "semantic" / "candidate_summaries"
OUTPUT_JSONL = LAKE_SEMANTIC_DIR / "candidate_summaries.jsonl"
OUTPUT_PARQUET = LAKE_SEMANTIC_DIR / "candidate_summaries.parquet"
OUTPUT_GOLD_CSV = DATA_GOLD / "semantic_candidate_summaries.csv"

OUTPUT_COLUMNS = [
    "candidate_name",
    "summary_type",
    "generated_text",
    "input_facts_json",
    "caveats_used",
    "prompt_version",
    "model_name",
    "generated_at",
    "run_id",
    "review_status",
]

MOCK_MODEL_NAME = "mock-template-v1"
DEFAULT_LIVE_MODEL = "claude-sonnet-5"

REVIEW_STATUS_MOCK = "auto_generated"
REVIEW_STATUS_LIVE = "pending_review"

CAVEAT_SEPARATOR = " || "

PARTY_LABELS = {"R": "Republican", "D": "Democratic", "I": "Independent"}

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("generate_candidate_explanations")


# ---------------------------------------------------------------------------
# Canonical caveat text. These are the required-caveat sentences requirements
# 5-7 refer to. They are defined once here and imported by
# evaluate_llm_outputs.py so the "what must be present" rule has a single
# source of truth instead of being duplicated between generation and checks.
# ---------------------------------------------------------------------------

COURT_LEVEL_CAVEAT = (
    "OCA metrics are court-level context for the seat, not individual "
    "candidate performance."
)
REPORT_PERIOD_CAVEAT = (
    "TEC contribution and expenditure values are latest available "
    "report-period totals, not lifetime or full-cycle totals."
)
SOURCE_SCOPED_CAVEAT = (
    "SCJC result is source-scoped: it reflects only the public sanctions "
    "pages checked for this prototype, not a comprehensive disciplinary "
    "record."
)

CAVEAT_TEXT: dict[str, str] = {
    "court_level": COURT_LEVEL_CAVEAT,
    "report_period": REPORT_PERIOD_CAVEAT,
    "source_scoped": SOURCE_SCOPED_CAVEAT,
}

# Which caveat keys (from CAVEAT_TEXT) each summary_type is required to carry.
# Read by evaluate_llm_outputs.py as well, so keep this the single source of
# truth for the "must include the X caveat" requirements.
SUMMARY_TYPE_REQUIRED_CAVEATS: dict[str, list[str]] = {
    "candidate_overview": [],
    "professional_background": [],
    "finance_explanation": ["report_period"],
    "court_context_explanation": ["court_level"],
    "public_record_notes_explanation": ["source_scoped"],
}

SUMMARY_TYPES = list(SUMMARY_TYPE_REQUIRED_CAVEATS.keys())

FOCUS_INSTRUCTIONS = {
    "candidate_overview": (
        "Give a short general orientation: the office/court they are running "
        "for, their party, incumbent or challenger status, and how complete "
        "this prototype's record is for them (a data-completeness note, not "
        "a candidate rating)."
    ),
    "professional_background": (
        "Focus only on the public State Bar of Texas information: bar "
        "status, license date on record, and the public discipline flag "
        "captured for this profile."
    ),
}


# ---------------------------------------------------------------------------
# Prompt template loading
# ---------------------------------------------------------------------------


def parse_prompt_file(path: Path) -> dict[str, Any]:
    """Parse a prompt markdown file's simple YAML-style frontmatter + body.

    Frontmatter supports scalar `key: value` lines and single-line
    `key: [a, b, c]` lists. This is intentionally hand-rolled rather than a
    PyYAML dependency, since the frontmatter here is trivial.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path} is missing '---' YAML-style frontmatter")
    _, frontmatter_block, body = text.split("---\n", 2)

    meta: dict[str, Any] = {}
    for line in frontmatter_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            meta[key] = [v.strip() for v in inner.split(",") if v.strip()] if inner else []
        else:
            meta[key] = value

    meta["body"] = body.strip()
    return meta


def load_prompts() -> dict[str, dict[str, Any]]:
    """Load every prompt file, keyed by the prompt file's stem."""
    return {p.stem: parse_prompt_file(p) for p in sorted(PROMPTS_DIR.glob("*_prompt.md"))}


PROMPT_FILE_FOR_SUMMARY_TYPE = {
    "candidate_overview": "candidate_summary_prompt",
    "professional_background": "candidate_summary_prompt",
    "finance_explanation": "finance_explanation_prompt",
    "court_context_explanation": "court_context_prompt",
    "public_record_notes_explanation": "public_record_notes_prompt",
}


# ---------------------------------------------------------------------------
# Loading gold inputs
# ---------------------------------------------------------------------------


def load_csv_with_string_ids(csv_path: Path, string_columns: set[str]) -> pd.DataFrame:
    """Read a CSV, forcing known identifier columns (e.g. filer_id) to stay text."""
    header = pd.read_csv(csv_path, nrows=0).columns
    dtype = {col: str for col in string_columns if col in header}
    return pd.read_csv(csv_path, dtype=dtype)


def load_gold_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    for path in (GOLD_DOSSIERS, GOLD_READINESS, GOLD_RISK_SIGNALS):
        if not path.exists():
            raise FileNotFoundError(
                f"Missing required gold input: {path.relative_to(REPO_ROOT)}. "
                "The LLM explanation layer must run after the gold layer is "
                "built and validated (see docs/llm_explanation_layer.md)."
            )
    dossiers_df = load_csv_with_string_ids(GOLD_DOSSIERS, {"filer_id"})
    readiness_df = pd.read_csv(GOLD_READINESS)
    risk_df = pd.read_csv(GOLD_RISK_SIGNALS)
    return dossiers_df, readiness_df, risk_df


def risk_rows_for_candidate(risk_df: pd.DataFrame, candidate_name: str) -> list[dict[str, Any]]:
    subset = risk_df[risk_df["candidate_name"] == candidate_name]
    return subset.to_dict(orient="records")


def readiness_row_for_candidate(readiness_df: pd.DataFrame, candidate_name: str) -> dict[str, Any] | None:
    subset = readiness_df[readiness_df["candidate_name"] == candidate_name]
    if subset.empty:
        return None
    return subset.iloc[0].to_dict()


def optional_caveats_from_risk(
    risk_rows: list[dict[str, Any]], risk_types: list[str]
) -> list[str]:
    """Pull risk_message text for given risk_type values, in file order."""
    return [
        str(row["risk_message"])
        for row in risk_rows
        if row.get("risk_type") in risk_types and pd.notna(row.get("risk_message"))
    ]


def clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


# ---------------------------------------------------------------------------
# Fact + caveat construction per summary_type (source-grounded: every value
# here traces back to a gold CSV column, nothing is hardcoded per candidate)
# ---------------------------------------------------------------------------


def build_facts_and_caveats(
    summary_type: str,
    dossier_row: dict[str, Any],
    readiness_row: dict[str, Any] | None,
    risk_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Return (input_facts, required_caveat_texts, optional_caveat_texts)."""
    required = [CAVEAT_TEXT[key] for key in SUMMARY_TYPE_REQUIRED_CAVEATS[summary_type]]

    if summary_type == "candidate_overview":
        facts = {
            "party_code": clean_value(dossier_row.get("party")),
            "court_name": clean_value(dossier_row.get("court_name")),
            "court_type": clean_value(dossier_row.get("court_type")),
            "incumbent_status": clean_value(dossier_row.get("incumbent_status")),
            "overall_confidence": clean_value(dossier_row.get("overall_confidence")),
            "fields_complete": clean_value(readiness_row.get("fields_complete")) if readiness_row else None,
            "fields_possible": clean_value(readiness_row.get("fields_possible")) if readiness_row else None,
            "readiness_label": clean_value(readiness_row.get("readiness_label")) if readiness_row else None,
        }
        optional = optional_caveats_from_risk(risk_rows, ["source_link_specificity"])
        return facts, required, optional

    if summary_type == "professional_background":
        facts = {
            "bar_status": clean_value(dossier_row.get("bar_status")),
            "licensed_since": clean_value(dossier_row.get("licensed_since")),
            "public_discipline_flag": clean_value(dossier_row.get("public_discipline_flag")),
        }
        return facts, required, []

    if summary_type == "finance_explanation":
        facts = {
            "filer_id": clean_value(dossier_row.get("filer_id")),
            "total_contributions": clean_value(dossier_row.get("total_contributions")),
            "total_expenditures": clean_value(dossier_row.get("total_expenditures")),
        }
        optional = optional_caveats_from_risk(risk_rows, ["source_link_specificity"])
        return facts, required, optional

    if summary_type == "court_context_explanation":
        facts = {
            "court_name": clean_value(dossier_row.get("court_name")),
            "oca_case_category": clean_value(dossier_row.get("oca_case_category")),
            "active_pending_total": clean_value(dossier_row.get("active_pending_total")),
            "long_pending_count": clean_value(dossier_row.get("long_pending_count")),
            "long_pending_threshold": clean_value(dossier_row.get("long_pending_threshold")),
            "long_pending_pct": clean_value(dossier_row.get("long_pending_pct")),
            "incumbent_status": clean_value(dossier_row.get("incumbent_status")),
        }
        optional = optional_caveats_from_risk(
            risk_rows,
            ["challenger_interpretation", "incumbent_interpretation", "high_long_pending_context"],
        )
        return facts, required, optional

    if summary_type == "public_record_notes_explanation":
        facts = {
            "scjc_result": clean_value(dossier_row.get("scjc_result")),
            "public_discipline_flag": clean_value(dossier_row.get("public_discipline_flag")),
        }
        optional = optional_caveats_from_risk(risk_rows, ["source_link_specificity"])
        return facts, required, optional

    raise ValueError(f"Unknown summary_type: {summary_type}")


# ---------------------------------------------------------------------------
# Mock (deterministic template) rendering — default mode, no API key needed
# ---------------------------------------------------------------------------


def _fmt_money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "an amount not available in this prototype's records"


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "a count not available in this prototype's records"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "a percentage not available in this prototype's records"


def _or_not_available(value: Any) -> str:
    return str(value) if value not in (None, "") else "not available in this prototype's records"


def render_mock_text(
    summary_type: str,
    candidate_name: str,
    facts: dict[str, Any],
    required_caveats: list[str],
    optional_caveats: list[str],
) -> str:
    caveat_sentences = " ".join(required_caveats + optional_caveats)

    if summary_type == "candidate_overview":
        party = PARTY_LABELS.get(str(facts.get("party_code") or ""), "an unspecified-party")
        court_name = _or_not_available(facts.get("court_name"))
        incumbent_status = str(facts.get("incumbent_status") or "candidate").lower()
        fields_complete = facts.get("fields_complete")
        fields_possible = facts.get("fields_possible")
        readiness_label = facts.get("readiness_label")
        text = (
            f"{candidate_name} is listed in this prototype as a {party} "
            f"candidate for the {court_name}, running as a(n) "
            f"{incumbent_status}. This profile draws on public State Bar "
            f"records, Texas Ethics Commission campaign finance filings, "
            f"OCA court-level case data, and an SCJC public sanctions check."
        )
        if fields_complete is not None and fields_possible is not None:
            text += (
                f" {_fmt_int(fields_complete)} of {_fmt_int(fields_possible)} "
                f"tracked prototype fields were available for this candidate"
                + (f" ({readiness_label} data completeness)" if readiness_label else "")
                + ", which describes how much of the record this prototype "
                "found, not a rating of the candidate."
            )
        return text.strip()

    if summary_type == "professional_background":
        bar_status = _or_not_available(facts.get("bar_status"))
        licensed_since = _or_not_available(facts.get("licensed_since"))
        discipline_flag = _or_not_available(facts.get("public_discipline_flag"))
        return (
            f"According to the State Bar of Texas public profile referenced "
            f'in this prototype, {candidate_name}\'s bar status is listed as '
            f'"{bar_status}", with a license date on record of '
            f"{licensed_since}. The public discipline flag captured for "
            f'this profile is "{discipline_flag}", reflecting only what was '
            f"found on that public page at the time of the check."
        ).strip()

    if summary_type == "finance_explanation":
        filer_id = _or_not_available(facts.get("filer_id"))
        contributions = _fmt_money(facts.get("total_contributions"))
        expenditures = _fmt_money(facts.get("total_expenditures"))
        return (
            f"Texas Ethics Commission (TEC) filer records referenced in "
            f"this prototype (filer ID {filer_id}) show total "
            f"contributions of {contributions} and total expenditures of "
            f"{expenditures}. {caveat_sentences}"
        ).strip()

    if summary_type == "court_context_explanation":
        court_name = _or_not_available(facts.get("court_name"))
        case_category = _or_not_available(facts.get("oca_case_category"))
        active_total = facts.get("active_pending_total")
        long_count = facts.get("long_pending_count")
        long_pct = facts.get("long_pending_pct")
        if active_total is not None and long_count is not None and long_pct is not None:
            numbers_sentence = (
                f"OCA court-level data referenced in this prototype shows "
                f"{_fmt_int(long_count)} of {_fmt_int(active_total)} active "
                f"pending {case_category} cases at the {court_name} "
                f"classified as long-pending, about {_fmt_pct(long_pct)}."
            )
        else:
            numbers_sentence = (
                f"OCA court-level case data for the {court_name} was not "
                f"fully available in this prototype's records."
            )
        return f"{numbers_sentence} {caveat_sentences}".strip()

    if summary_type == "public_record_notes_explanation":
        scjc_result = _or_not_available(facts.get("scjc_result"))
        return (
            f"The State Commission on Judicial Conduct (SCJC) public "
            f'sanctions check referenced in this prototype returned: '
            f'"{scjc_result}". {caveat_sentences}'
        ).strip()

    raise ValueError(f"Unknown summary_type: {summary_type}")


# ---------------------------------------------------------------------------
# Live LLM rendering — behind an env var, never required for tests/CI
# ---------------------------------------------------------------------------


def render_live_text(
    prompt_meta: dict[str, Any],
    summary_type: str,
    candidate_name: str,
    facts: dict[str, Any],
    required_caveats: list[str],
    optional_caveats: list[str],
    model_name: str,
) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "SPARTAN_LLM_MODE=live requires the 'anthropic' package "
            "(pip install anthropic). Use mock mode if it is not installed."
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY must be set to use SPARTAN_LLM_MODE=live.")

    body = prompt_meta["body"]
    focus = FOCUS_INSTRUCTIONS.get(summary_type, "")
    system_prompt = (
        body.replace("{{FOCUS_INSTRUCTIONS}}", focus)
        .replace("{{CANDIDATE_NAME}}", candidate_name)
        .replace("{{INPUT_FACTS_JSON}}", json.dumps(facts, indent=2, default=str))
        .replace("{{REQUIRED_CAVEATS_JSON}}", json.dumps(required_caveats, indent=2))
        .replace("{{OPTIONAL_CAVEATS_JSON}}", json.dumps(optional_caveats, indent=2))
    )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model_name,
        max_tokens=400,
        system=system_prompt,
        messages=[{"role": "user", "content": "Write the explanation now."}],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def generate_run_id() -> str:
    return datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def generate_all(mode: str, model_name: str, run_id: str) -> list[dict[str, Any]]:
    dossiers_df, readiness_df, risk_df = load_gold_inputs()
    prompts = load_prompts()
    generated_at = datetime.now(timezone.utc).isoformat()
    review_status = REVIEW_STATUS_MOCK if mode == "mock" else REVIEW_STATUS_LIVE

    records: list[dict[str, Any]] = []
    for _, dossier_row_series in dossiers_df.iterrows():
        dossier_row = dossier_row_series.to_dict()
        candidate_name = dossier_row["candidate_name"]
        readiness_row = readiness_row_for_candidate(readiness_df, candidate_name)
        risk_rows = risk_rows_for_candidate(risk_df, candidate_name)

        for summary_type in SUMMARY_TYPES:
            prompt_key = PROMPT_FILE_FOR_SUMMARY_TYPE[summary_type]
            prompt_meta = prompts[prompt_key]
            facts, required_caveats, optional_caveats = build_facts_and_caveats(
                summary_type, dossier_row, readiness_row, risk_rows
            )

            if mode == "mock":
                generated_text = render_mock_text(
                    summary_type, candidate_name, facts, required_caveats, optional_caveats
                )
            elif mode == "live":
                generated_text = render_live_text(
                    prompt_meta,
                    summary_type,
                    candidate_name,
                    facts,
                    required_caveats,
                    optional_caveats,
                    model_name,
                )
            else:
                raise ValueError(f"Unknown mode: {mode}")

            records.append(
                {
                    "candidate_name": candidate_name,
                    "summary_type": summary_type,
                    "generated_text": generated_text,
                    "input_facts_json": json.dumps(facts, sort_keys=True, default=str),
                    "caveats_used": CAVEAT_SEPARATOR.join(required_caveats + optional_caveats),
                    "prompt_version": prompt_meta["prompt_version"],
                    "model_name": model_name if mode == "live" else MOCK_MODEL_NAME,
                    "generated_at": generated_at,
                    "run_id": run_id,
                    "review_status": review_status,
                }
            )

    return records


def write_outputs(records: list[dict[str, Any]]) -> None:
    df = pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)

    LAKE_SEMANTIC_DIR.mkdir(parents=True, exist_ok=True)
    DATA_GOLD.mkdir(parents=True, exist_ok=True)

    with OUTPUT_JSONL.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    logger.info("Wrote %d rows to %s", len(records), OUTPUT_JSONL.relative_to(REPO_ROOT))

    df.to_parquet(OUTPUT_PARQUET, index=False)
    logger.info("Wrote %d rows to %s", len(records), OUTPUT_PARQUET.relative_to(REPO_ROOT))

    df.to_csv(OUTPUT_GOLD_CSV, index=False)
    logger.info("Wrote %d rows to %s", len(records), OUTPUT_GOLD_CSV.relative_to(REPO_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["mock", "live"],
        default=os.environ.get("SPARTAN_LLM_MODE", "mock"),
        help="mock (default, deterministic templates) or live (calls the Anthropic API)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("SPARTAN_LLM_MODEL", DEFAULT_LIVE_MODEL),
        help="Model name to record and to call in live mode.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Override the generated run_id (defaults to a timestamp-based id).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = args.run_id or generate_run_id()
    logger.info("Generating candidate explanations in %s mode (run_id=%s)", args.mode, run_id)
    records = generate_all(mode=args.mode, model_name=args.model, run_id=run_id)
    write_outputs(records)
    logger.info("Done: %d explanation rows across %d summary types.", len(records), len(SUMMARY_TYPES))


if __name__ == "__main__":
    main()
