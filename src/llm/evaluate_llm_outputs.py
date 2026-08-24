"""
Evaluate generated LLM/mock candidate explanations for policy compliance.

This is a gate, not a generator: it never rewrites or filters generated
text, it only reports whether each row (a) avoids a banned-phrase list
(endorsements, rankings, predictions, accusations, candidate-quality
judgments) and (b) contains the caveat text its summary_type is required to
carry, per SUMMARY_TYPE_REQUIRED_CAVEATS in generate_candidate_explanations.py.

Run from the project root:
    python src/llm/evaluate_llm_outputs.py
    python src/llm/evaluate_llm_outputs.py --input data/lake/semantic/candidate_summaries/candidate_summaries.jsonl

Exits with status 1 if any row fails, so this can be used as a CI gate
before semantic_candidate_summaries.csv is treated as safe to publish.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.llm.generate_candidate_explanations import (  # noqa: E402
    CAVEAT_TEXT,
    SUMMARY_TYPE_REQUIRED_CAVEATS,
)

DEFAULT_INPUT = REPO_ROOT / "data" / "gold" / "semantic_candidate_summaries.csv"
REPORT_DIR = REPO_ROOT / "reports"
REPORT_OUTPUT = REPORT_DIR / "llm_output_evaluation_report.csv"

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("evaluate_llm_outputs")


# ---------------------------------------------------------------------------
# Banned phrase list: endorsements, rankings/comparisons, predictions,
# accusations, and candidate-quality judgments. Every generated summary must
# avoid all of these regardless of summary_type (requirement #4).
# ---------------------------------------------------------------------------

BANNED_PHRASES: dict[str, str] = {
    # Endorsements / vote steering
    "vote for": r"\bvote for\b",
    "vote against": r"\bvote against\b",
    "we endorse": r"\bwe endorse\b",
    "endorse": r"\bendorse(s|d|ment)?\b",
    "recommend voting": r"\brecommend(ed)? voting\b",
    "recommend electing": r"\brecommend(ed)? electing\b",
    "should be elected": r"\bshould be elected\b",
    # Ranking / comparison against other candidates
    "best candidate": r"\bbest candidate\b",
    "worst candidate": r"\bworst candidate\b",
    "top candidate": r"\btop candidate\b",
    "better candidate": r"\bbetter candidate\b",
    "worse candidate": r"\bworse candidate\b",
    "more qualified": r"\bmore qualified\b",
    "less qualified": r"\bless qualified\b",
    "better than": r"\bbetter than\b",
    "worse than": r"\bworse than\b",
    "outperforms": r"\boutperforms?\b",
    "ranked": r"\branked\b",
    # Predictions
    "will win": r"\bwill win\b",
    "will lose": r"\bwill lose\b",
    "likely to win": r"\blikely to win\b",
    "expected to win": r"\bexpected to win\b",
    "predicted to win": r"\bpredicted to win\b",
    "poised to win": r"\bpoised to win\b",
    # Accusations. Note: bare "criminal" is deliberately NOT banned here —
    # several real court names/types in this dataset are legitimately named
    # "Criminal Court" / "Criminal District Court", and that is a neutral
    # jurisdiction label, not an accusation against the candidate. These
    # patterns instead target phrasing that accuses a person of wrongdoing.
    "guilty": r"\bguilty\b",
    "corrupt": r"\bcorrupt(ion)?\b",
    "criminal record": r"\bcriminal record\b",
    "criminal history": r"\bcriminal history\b",
    "criminal charges": r"\bcriminal charges\b",
    "committed a crime": r"\bcommitted (a |the )?crimes?\b",
    "convicted": r"\bconvicted\b",
    "unethical": r"\bunethical\b",
    "misconduct": r"\bmisconduct\b",
    "wrongdoing": r"\bwrongdoing\b",
    "fraud": r"\bfraud(ulent)?\b",
    # Candidate-quality judgments
    "excellent candidate": r"\bexcellent candidate\b",
    "outstanding candidate": r"\boutstanding candidate\b",
    "unfit": r"\bunfit\b",
    "incompetent": r"\bincompetent\b",
    "highly qualified": r"\bhighly qualified\b",
    "well qualified": r"\bwell[- ]qualified\b",
    "poorly qualified": r"\bpoorly qualified\b",
    "strong candidate": r"\bstrong candidate\b",
    "weak candidate": r"\bweak candidate\b",
    "trustworthy": r"\btrustworthy\b",
    "untrustworthy": r"\buntrustworthy\b",
    "dishonest": r"\bdishonest\b",
}

_COMPILED_BANNED_PHRASES = {label: re.compile(pattern, re.IGNORECASE) for label, pattern in BANNED_PHRASES.items()}


@dataclass
class RowEvaluation:
    candidate_name: str
    summary_type: str
    run_id: str
    banned_phrases_found: list[str] = field(default_factory=list)
    missing_required_caveats: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.banned_phrases_found and not self.missing_required_caveats


def find_banned_phrases(text: str) -> list[str]:
    """Return the labels of every banned phrase found in text, in a stable order."""
    if not isinstance(text, str):
        return []
    return [label for label, pattern in _COMPILED_BANNED_PHRASES.items() if pattern.search(text)]


def find_missing_required_caveats(summary_type: str, text: str) -> list[str]:
    """Return the required caveat texts that are NOT present verbatim in text.

    Unknown summary_types are treated as having no required caveats, since
    this function only enforces requirements 5-7; unrelated summary_types
    (e.g. future additions) are out of scope here.
    """
    if not isinstance(text, str):
        text = ""
    required_keys = SUMMARY_TYPE_REQUIRED_CAVEATS.get(summary_type, [])
    return [CAVEAT_TEXT[key] for key in required_keys if CAVEAT_TEXT[key] not in text]


def evaluate_row(candidate_name: str, summary_type: str, generated_text: str, run_id: str = "") -> RowEvaluation:
    return RowEvaluation(
        candidate_name=candidate_name,
        summary_type=summary_type,
        run_id=run_id,
        banned_phrases_found=find_banned_phrases(generated_text),
        missing_required_caveats=find_missing_required_caveats(summary_type, generated_text),
    )


def load_records(input_path: Path) -> list[dict]:
    if input_path.suffix == ".jsonl":
        with input_path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    if input_path.suffix in (".csv", ".parquet"):
        df = pd.read_csv(input_path) if input_path.suffix == ".csv" else pd.read_parquet(input_path)
        return df.to_dict(orient="records")
    raise ValueError(f"Unsupported input file type: {input_path}")


def evaluate_records(records: list[dict]) -> list[RowEvaluation]:
    return [
        evaluate_row(
            candidate_name=record.get("candidate_name", ""),
            summary_type=record.get("summary_type", ""),
            generated_text=record.get("generated_text", ""),
            run_id=record.get("run_id", ""),
        )
        for record in records
    ]


def build_report(evaluations: list[RowEvaluation]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candidate_name": ev.candidate_name,
                "summary_type": ev.summary_type,
                "run_id": ev.run_id,
                "passed": ev.passed,
                "banned_phrases_found": " | ".join(ev.banned_phrases_found),
                "missing_required_caveats": " | ".join(ev.missing_required_caveats),
            }
            for ev in evaluations
        ]
    )


def _display_path(path: Path) -> Path:
    """Render a path relative to the repo root when possible, for readable logs."""
    return path.relative_to(REPO_ROOT) if path.is_absolute() and path.is_relative_to(REPO_ROOT) else path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to a .csv, .parquet, or .jsonl file of generated candidate explanations.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
        return 1

    records = load_records(args.input)
    evaluations = evaluate_records(records)
    report_df = build_report(evaluations)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_df.to_csv(REPORT_OUTPUT, index=False)

    failures = [ev for ev in evaluations if not ev.passed]
    logger.info(
        "Evaluated %d rows from %s: %d passed, %d failed. Report: %s",
        len(evaluations),
        _display_path(args.input),
        len(evaluations) - len(failures),
        len(failures),
        _display_path(REPORT_OUTPUT),
    )
    for ev in failures:
        logger.warning(
            "FAILED %s / %s (run_id=%s): banned=%s missing_caveats=%s",
            ev.candidate_name,
            ev.summary_type,
            ev.run_id,
            ev.banned_phrases_found,
            ev.missing_required_caveats,
        )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
