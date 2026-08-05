"""
Dagster assets for the Spartan Judicial campaign data platform.

This module wraps the platform's existing standalone scripts as Dagster
software-defined assets, so the one-command pipeline
(src/pipeline/run_pipelne.py) also has a formal, asset-based orchestration
layer with per-step logging, dependency tracking, and a UI (`dagster dev`).

Every asset here runs its underlying script as a subprocess:
    python -m <module.path>
executed with cwd set to the repository root. Subprocess execution (rather
than importing each script's main() function in-process) is used
deliberately:

- It exactly mirrors how src/pipeline/run_pipelne.py already invokes these
  scripts, so behavior does not change between the two runners.
- Several scripts (e.g. validate_target_3_dossier.py) use an absolute
  import like `from src.schemas.candidate_dossier import CandidateDossier`.
  That import only resolves when the repository root is on sys.path, which
  is guaranteed by running `python -m <module>` with cwd=<repo root>, but
  would NOT be guaranteed by importing the module directly inside the
  long-running Dagster process.
- Each step gets a clean interpreter and working directory, so there is no
  risk of module-level state (e.g. path constants computed at import time)
  leaking between pipeline steps.

The dependency order below matches the CSV pipeline's step order plus the
newer Parquet lakehouse / DuckDB / SQL mart storage layer:

    clean_target_dossier
        -> validate_silver_dossier
        -> build_gold_outputs
        -> validate_gold_outputs
        -> generate_evaluation_report
        -> export_lakehouse_layers
        -> build_duckdb_warehouse
        -> run_sql_models
"""

import subprocess
import sys
from pathlib import Path

from dagster import AssetExecutionContext, asset

# orchestration/dagster_project/assets.py -> repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_module(context: AssetExecutionContext, module: str, step_name: str) -> None:
    """Run one pipeline script as `python -m <module>` from the repo root.

    Logs the step's stdout/stderr through the asset's Dagster logger and
    raises a RuntimeError (failing the asset materialization) if the
    subprocess exits with a non-zero status.

    Args:
        context: The asset execution context, used for step-scoped logging.
        module: Dotted module path to run, e.g. "src.transformations.clean_target_3_dossier".
        step_name: Human-readable step name, used in log messages and errors.
    """
    context.log.info(f"Starting step: {step_name} (python -m {module})")

    result = subprocess.run(
        [sys.executable, "-m", module],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.info(result.stderr)

    if result.returncode != 0:
        context.log.error(f"Step failed: {step_name} (exit code {result.returncode})")
        raise RuntimeError(f"{step_name} failed with exit code {result.returncode}")

    context.log.info(f"Completed step: {step_name}")


@asset(
    group_name="spartan_pipeline",
    description=(
        "Clean the raw target-three campaign dossier CSV into a standardized "
        "silver table."
    ),
)
def clean_target_dossier(context: AssetExecutionContext) -> None:
    """Run src/transformations/clean_target_3_dossier.py.

    Reads data/bronze/target_3_campaign_dossier_raw.csv and writes the
    cleaned table to data/silver/target_3_campaign_dossier_clean.csv.
    """
    _run_module(
        context,
        "src.transformations.clean_target_3_dossier",
        "Clean target-three dossier",
    )


@asset(
    group_name="spartan_pipeline",
    deps=[clean_target_dossier],
    description=(
        "Validate the cleaned silver dossier rows against the CandidateDossier "
        "Pydantic schema."
    ),
)
def validate_silver_dossier(context: AssetExecutionContext) -> None:
    """Run src/validation/validate_target_3_dossier.py.

    Validates data/silver/target_3_campaign_dossier_clean.csv row by row and
    writes reports/target_3_validation_report.csv.
    """
    _run_module(
        context,
        "src.validation.validate_target_3_dossier",
        "Validate silver target-three dossier",
    )


@asset(
    group_name="spartan_pipeline",
    deps=[validate_silver_dossier],
    description=(
        "Build the gold candidate dossier, campaign readiness, and risk-signal "
        "outputs from the validated silver dossier."
    ),
)
def build_gold_outputs(context: AssetExecutionContext) -> None:
    """Run src/evaluation/build_gold_outputs.py.

    Reads the silver dossier and writes:
    - data/gold/gold_candidate_dossiers.csv
    - data/gold/gold_campaign_readiness.csv
    - data/gold/gold_risk_signals.csv
    """
    _run_module(
        context,
        "src.evaluation.build_gold_outputs",
        "Build gold outputs",
    )


@asset(
    group_name="spartan_pipeline",
    deps=[build_gold_outputs],
    description=(
        "Validate that the generated gold-layer CSV files exist and contain "
        "the required columns."
    ),
)
def validate_gold_outputs(context: AssetExecutionContext) -> None:
    """Run src/validation/validate_gold_outputs.py.

    Checks each gold CSV file for existence and required columns, writing
    reports/gold_outputs_validation_report.csv.
    """
    _run_module(
        context,
        "src.validation.validate_gold_outputs",
        "Validate gold outputs",
    )


@asset(
    group_name="spartan_pipeline",
    deps=[validate_gold_outputs],
    description=(
        "Generate the Markdown evaluation report summarizing the target-three "
        "prototype's readiness scores, risk signals, and caveats."
    ),
)
def generate_evaluation_report(context: AssetExecutionContext) -> None:
    """Run src/evaluation/generate_evaluation_report.py.

    Reads the gold outputs and validation report, and writes
    reports/target_3_evaluation_report.md.
    """
    _run_module(
        context,
        "src.evaluation.generate_evaluation_report",
        "Generate evaluation report",
    )


@asset(
    group_name="spartan_lakehouse",
    deps=[generate_evaluation_report],
    description=(
        "Export the bronze, silver, and gold CSV layers to Parquet under "
        "data/lake/, plus a point-in-time snapshot for this run."
    ),
)
def export_lakehouse_layers(context: AssetExecutionContext) -> None:
    """Run src/storage/export_lakehouse_layers.py.

    Reads the existing bronze/silver/gold CSVs (read-only), adds run_id and
    exported_at lineage columns, and writes Parquet files under
    data/lake/{bronze,silver,gold}/ and data/lake/snapshots/run_id=<run_id>/.
    """
    _run_module(
        context,
        "src.storage.export_lakehouse_layers",
        "Export lakehouse layers",
    )


@asset(
    group_name="spartan_lakehouse",
    deps=[export_lakehouse_layers],
    description=(
        "Build the local DuckDB warehouse with views over the Parquet "
        "lakehouse layer."
    ),
)
def build_duckdb_warehouse(context: AssetExecutionContext) -> None:
    """Run src/storage/build_duckdb.py.

    Creates data/warehouse/spartan_campaign.duckdb and views
    (bronze_target_3_dossier, silver_target_3_dossier,
    gold_candidate_dossiers, gold_campaign_readiness, gold_risk_signals)
    over the exported Parquet files, then logs a row-count sanity check.
    """
    _run_module(
        context,
        "src.storage.build_duckdb",
        "Build DuckDB warehouse",
    )


@asset(
    group_name="spartan_lakehouse",
    deps=[build_duckdb_warehouse],
    description=(
        "Run the dbt-style SQL staging and mart models over the DuckDB "
        "warehouse and export the mart outputs."
    ),
)
def run_sql_models(context: AssetExecutionContext) -> None:
    """Run src/storage/run_sql_models.py.

    Runs the sql/staging/*.sql and sql/marts/*.sql models against the
    DuckDB warehouse, then exports each mart to
    data/lake/gold/sql_marts/*.parquet and data/gold/sql_marts/*.csv.
    """
    _run_module(
        context,
        "src.storage.run_sql_models",
        "Run SQL staging and mart models",
    )
