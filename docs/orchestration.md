# Orchestration

## Overview

The Spartan Judicial data platform has two ways to run its pipeline:

1. **`src/pipeline/run_pipelne.py`** — the original lightweight, one-command
   runner. It runs each script in sequence via `subprocess` and writes a run
   log to `reports/pipeline_runs/`. This still exists and still works; it
   has not been changed.
2. **Dagster (`orchestration/dagster_project/`)** — a formal, asset-based
   orchestration layer on top of the same underlying scripts. It adds
   per-step logging, a dependency graph, a UI for inspecting runs, and the
   ability to re-run or select individual steps.

Both runners call the exact same underlying scripts. Dagster does not
replace or duplicate any pipeline logic — it wraps the existing scripts as
software-defined assets.

## Asset graph

```
clean_target_dossier
      ↓
validate_silver_dossier
      ↓
build_gold_outputs
      ↓
validate_gold_outputs
      ↓
generate_evaluation_report
      ↓
export_lakehouse_layers
      ↓
build_duckdb_warehouse
      ↓
run_sql_models
```

| Asset | Underlying script | What it does |
|---|---|---|
| `clean_target_dossier` | `src/transformations/clean_target_3_dossier.py` | Cleans the raw bronze dossier CSV into the silver table. |
| `validate_silver_dossier` | `src/validation/validate_target_3_dossier.py` | Validates the silver dossier rows against the `CandidateDossier` Pydantic schema. |
| `build_gold_outputs` | `src/evaluation/build_gold_outputs.py` | Builds the gold candidate dossier, campaign readiness, and risk-signal CSVs. |
| `validate_gold_outputs` | `src/validation/validate_gold_outputs.py` | Checks the gold CSVs for existence and required columns. |
| `generate_evaluation_report` | `src/evaluation/generate_evaluation_report.py` | Writes the Markdown evaluation report summarizing readiness and risk signals. |
| `export_lakehouse_layers` | `src/storage/export_lakehouse_layers.py` | Exports bronze/silver/gold CSVs to Parquet under `data/lake/`, plus a run snapshot. |
| `build_duckdb_warehouse` | `src/storage/build_duckdb.py` | Builds `data/warehouse/spartan_campaign.duckdb` with views over the Parquet layer. |
| `run_sql_models` | `src/storage/run_sql_models.py` | Runs the SQL staging + mart models and exports the mart outputs. |

The first five assets belong to the `spartan_pipeline` asset group; the last
three (lakehouse export, warehouse, SQL marts) belong to the
`spartan_lakehouse` asset group. Dependencies are declared with each
asset's `deps=[...]`, so Dagster always executes them in the order above
regardless of which subset is selected.

## How each asset runs its script

Every asset runs its underlying script as a subprocess:

```
python -m <module.path>
```

executed with the current working directory set to the repository root.
Subprocess execution (rather than importing each script's `main()`
in-process) was chosen deliberately:

- It exactly mirrors how `src/pipeline/run_pipelne.py` already invokes
  these scripts, so behavior is identical between the two runners.
- Some scripts (e.g. `validate_target_3_dossier.py`) use an absolute import
  such as `from src.schemas.candidate_dossier import CandidateDossier`.
  That import only resolves correctly when the repository root is on
  `sys.path`, which running `python -m <module>` with the repo root as the
  working directory guarantees. Invoking the script by file path (e.g.
  `python src/validation/validate_target_3_dossier.py`) does **not**
  guarantee this and can fail with `ModuleNotFoundError: No module named
  'src'`.
- Each step gets a clean interpreter and working directory, so there is no
  risk of module-level state (e.g. path constants computed at import time)
  leaking between steps.

Step stdout/stderr is captured and logged through the Dagster asset logger,
and a non-zero exit code fails the asset materialization.

## Running it

Launch the Dagster UI from the repository root:

```bash
dagster dev -m orchestration.dagster_project.definitions
```

This opens the Dagster web UI (defaults to `http://localhost:3000`), where
you can materialize all assets, materialize a subset, or run the
`spartan_pipeline_job` job.

To materialize everything from the command line instead:

```bash
dagster asset materialize -m orchestration.dagster_project.definitions --select "*"
```

## Setup

Dagster and the Dagster webserver are listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

No cloud credentials or external services are required — everything runs
locally against the existing CSV files, the Parquet lakehouse layer, and the
local DuckDB warehouse file.
