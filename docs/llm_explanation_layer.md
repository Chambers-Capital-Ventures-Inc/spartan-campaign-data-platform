# LLM explanation layer

## What this is

This adds a **semantic explanation layer**: short, plain-English
paragraphs that explain the already-validated gold facts about each
candidate, for a non-technical voter. It is purely additive — it reads
`data/gold/*.csv`, writes new files, and does **not** change
`app/streamlit/dashboard.py` or the existing Postgres serving layer
(`src/storage/export_to_postgres.py`, see
[serving_layer.md](serving_layer.md)). Wiring it into either of those is
future work, described in [How this will eventually be consumed](#how-this-will-eventually-be-consumed)
below.

```
data/gold/gold_candidate_dossiers.csv   ─┐
data/gold/gold_campaign_readiness.csv   ─┼─► src/llm/generate_candidate_explanations.py ─► candidate_summaries.jsonl
data/gold/gold_risk_signals.csv         ─┘         │                                    ─► candidate_summaries.parquet
                                                    │                                    ─► semantic_candidate_summaries.csv
                                                    ▼
                                    src/llm/evaluate_llm_outputs.py ─► reports/llm_output_evaluation_report.csv
```

## The architecture rule: LLM runs after gold, never before

The generator only ever reads from `data/gold/*.csv` — files that have
already been through the pipeline's transformation and validation steps
(`src/evaluation/build_gold_outputs.py`,
`src/validation/validate_gold_outputs.py`). It never reads bronze or
silver data, never queries an external source, and never decides what a
fact *is*. Its only job is to phrase facts that are already decided.

Concretely:

- Every value that ends up in generated text traces back to a specific gold
  CSV column (see `build_facts_and_caveats()` in
  `src/llm/generate_candidate_explanations.py`). There is no per-candidate
  hardcoded text anywhere in this layer.
- If a fact is missing, the prompt/template says so explicitly ("not
  available in this prototype's records") instead of guessing.
- The model (real or mock) is never asked to decide facts, only to phrase
  a fixed JSON blob of facts and caveats into 2-4 sentences.

## Inputs and outputs

Inputs (all from the already-validated gold layer):

- `data/gold/gold_candidate_dossiers.csv`
- `data/gold/gold_campaign_readiness.csv`
- `data/gold/gold_risk_signals.csv`

Outputs (one row per candidate per `summary_type`):

- `data/lake/semantic/candidate_summaries/candidate_summaries.jsonl`
- `data/lake/semantic/candidate_summaries/candidate_summaries.parquet`
- `data/gold/semantic_candidate_summaries.csv`

All three outputs have the same schema:

| Column | Meaning |
|---|---|
| `candidate_name` | Matches `gold_candidate_dossiers.candidate_name` |
| `summary_type` | One of the five summary types below |
| `generated_text` | The plain-English paragraph |
| `input_facts_json` | The exact JSON facts blob the model/template was given — nothing in `generated_text` should reference a fact not in here |
| `caveats_used` | The caveat sentences actually included in `generated_text`, joined with `\|\|` |
| `prompt_version` | From the prompt file's frontmatter, e.g. `finance_explanation_v1` |
| `model_name` | `mock-template-v1` in mock mode, or the live model id (e.g. `claude-sonnet-5`) in live mode |
| `generated_at` | UTC ISO-8601 timestamp |
| `run_id` | `run_YYYYMMDDTHHMMSSZ`, matching the format used elsewhere in this repo (see `src/storage/export_lakehouse_layers.py`) |
| `review_status` | `auto_generated` (mock mode) or `pending_review` (live mode — LLM prose should be reviewed before being shown to a user) |

## Naming collision with the existing Postgres table — read this before wiring anything up

`sql/postgres/create_serving_tables.sql` already defines a table called
`semantic_candidate_summaries` with a **different, narrower** schema
(`candidate_name` primary key, `profile_summary` / `finance_summary` /
`court_context_summary` text columns, built by the deterministic template
functions already in `src/storage/export_to_postgres.py`). That table is
unrelated to this layer and is untouched by anything here.

The new `data/gold/semantic_candidate_summaries.csv` produced by this
layer is a long-format table (one row per candidate *and* summary type,
five summary types instead of three columns) with a richer schema
(`prompt_version`, `model_name`, `caveats_used`, `review_status`, etc.). If
this layer is later wired into Postgres, it should get its own table (for
example `llm_candidate_explanations`) rather than being merged into the
existing `semantic_candidate_summaries` table — the schemas don't match
and the existing table's deterministic-template guarantee ("no LLM") is a
documented property that other code may rely on.

## Summary types and prompts

Five `summary_type` values, generated from four prompt files in
`src/llm/prompts/` (the shared candidate-summary prompt covers two closely
related summary types via a `focus` parameter):

| `summary_type` | Prompt file | Required caveat |
|---|---|---|
| `candidate_overview` | `candidate_summary_prompt.md` (focus: overview) | none |
| `professional_background` | `candidate_summary_prompt.md` (focus: professional background) | none |
| `finance_explanation` | `finance_explanation_prompt.md` | report-period caveat |
| `court_context_explanation` | `court_context_prompt.md` | court-level caveat |
| `public_record_notes_explanation` | `public_record_notes_prompt.md` | source-scoped caveat |

Each prompt file has simple YAML-style frontmatter (`prompt_version`,
`summary_types`, `required_caveats`) followed by the actual prompt body.
`generate_candidate_explanations.py` parses the frontmatter with a small
hand-rolled parser (no new dependency) and uses it in both modes, so the
"what's required" logic is defined once, in the prompt file, not
duplicated in code.

The three required caveats are defined once, as constants, in
`src/llm/generate_candidate_explanations.py` (`COURT_LEVEL_CAVEAT`,
`REPORT_PERIOD_CAVEAT`, `SOURCE_SCOPED_CAVEAT`) and imported by
`evaluate_llm_outputs.py`, so generation and evaluation can never drift
out of sync on caveat wording.

## Neutrality rules

Same rules as the rest of this project (see the docstring at the top of
`app/streamlit/dashboard.py`), enforced both in the prompt files' "Hard
rules" sections and mechanically by `evaluate_llm_outputs.py`:

- No endorsements or vote-steering language.
- No ranking or comparing candidates against each other.
- No election predictions.
- No accusations of wrongdoing beyond what's literally in the gold data.
- No candidate-quality judgments (qualified/unqualified, strong/weak,
  trustworthy/untrustworthy, etc.). "Data completeness" describes how much
  of the record was found, never a rating of the candidate.

## Mock mode vs. live mode

**Mock mode is the default and requires no API key, no network access, and
no extra dependency.** It's what tests and CI use. `render_mock_text()`
builds the paragraph with deterministic Python string templates from the
same `input_facts` / `caveats` that would be sent to a live model, so mock
output already satisfies the same caveat and neutrality checks.

Live mode calls the Anthropic Messages API and is only used when
explicitly opted into:

| Env var | Effect |
|---|---|
| `SPARTAN_LLM_MODE` | `mock` (default) or `live` |
| `ANTHROPIC_API_KEY` | Required for live mode; live mode raises a clear error if unset |
| `SPARTAN_LLM_MODEL` | Overrides the model id recorded/called in live mode (default `claude-sonnet-5`) |

```bash
# Mock mode (default) — no API key needed
python src/llm/generate_candidate_explanations.py

# Live mode
export ANTHROPIC_API_KEY=sk-...
export SPARTAN_LLM_MODE=live
pip install anthropic   # not in requirements.txt — only needed for live mode
python src/llm/generate_candidate_explanations.py
```

The `anthropic` package is intentionally **not** added to
`requirements.txt`, since it's not needed for mock mode, tests, or CI.
Live mode does a lazy `import anthropic` and raises a clear
`RuntimeError` (not an import traceback) if it's missing.

Live-mode rows are always written with `review_status = pending_review` —
this layer treats LLM-authored prose as needing a human (or at minimum,
`evaluate_llm_outputs.py`) to sign off before being shown to a user.
Mock-mode rows get `auto_generated`, since they're fully deterministic
from already-validated facts.

## Evaluating generated output

```bash
python src/llm/evaluate_llm_outputs.py
# or point it at a specific file:
python src/llm/evaluate_llm_outputs.py --input data/lake/semantic/candidate_summaries/candidate_summaries.jsonl
```

This checks every row for:

1. Banned words/phrases — endorsements, rankings/comparisons, predictions,
   accusations, and candidate-quality judgments (see `BANNED_PHRASES` in
   `src/llm/evaluate_llm_outputs.py`).
2. The required caveat for that `summary_type`, present verbatim in
   `generated_text`.

It writes `reports/llm_output_evaluation_report.csv` (one row per
evaluated record, pass/fail plus what was found) and exits non-zero if any
row fails, so it can be used as a CI gate before treating
`semantic_candidate_summaries.csv` as safe to publish.

One deliberate design note: the banned-phrase list does **not** flag the
bare word "criminal", because several real court names/types in this
dataset are legitimately "Criminal Court" / "Criminal District Court" — a
neutral jurisdiction label, not an accusation. It instead flags more
specific accusatory phrasing ("criminal record", "criminal charges",
"convicted", etc.). See the regression tests in
`tests/test_evaluate_llm_outputs.py` for both cases.

Unit tests: `tests/test_evaluate_llm_outputs.py` covers banned-phrase
detection, required-caveat detection per `summary_type`, report shape, and
`main()`'s exit code in pass/fail scenarios. Run with:

```bash
python -m pytest tests/ -q
```

## How this will eventually be consumed

Nothing here changes `app/streamlit/dashboard.py` or the Postgres serving
layer yet. When that work happens:

- The Streamlit app would read `data/gold/semantic_candidate_summaries.csv`
  the same way it already reads the other gold CSVs, filtering to
  `review_status` values it trusts (e.g. `auto_generated`, or
  `pending_review` rows that have since been approved) and rendering
  `generated_text` per `summary_type` in the existing "About the data
  pipeline" style sections.
- If/when this is added to the Postgres serving layer, it should land as
  its own table (see [naming collision](#naming-collision-with-the-existing-postgres-table--read-this-before-wiring-anything-up)
  above), written by a new `build_llm_candidate_explanations()` function
  in `src/storage/export_to_postgres.py`, upserted on
  `(candidate_name, summary_type)`.
- Either integration should run `evaluate_llm_outputs.py` as a gate first
  and only surface rows that pass.

## Local setup

```bash
pip install -r requirements.txt   # mock mode needs nothing beyond this
```

No API key, network access, or extra dependency is required for mock
mode, tests, or CI — live mode is entirely optional infrastructure.
