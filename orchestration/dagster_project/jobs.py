"""
Dagster jobs for the Spartan Judicial campaign data platform.

Defines the job used to materialize the full pipeline (CSV cleaning ->
validation -> gold outputs -> validation -> evaluation report -> Parquet
lakehouse export -> DuckDB warehouse -> SQL marts) in one run, in the
dependency order declared in assets.py.
"""

from dagster import AssetSelection, define_asset_job

# Selects every asset defined in assets.py. Dagster resolves the actual
# execution order from each asset's `deps=[...]` declarations, so this job
# always runs clean_target_dossier through run_sql_models in the correct
# order even if new assets are added later.
spartan_pipeline_job = define_asset_job(
    name="spartan_pipeline_job",
    selection=AssetSelection.all(),
    description=(
        "Run the full Spartan Judicial data platform pipeline: clean -> "
        "validate silver -> build gold outputs -> validate gold -> generate "
        "evaluation report -> export lakehouse layers -> build DuckDB "
        "warehouse -> run SQL models."
    ),
)
