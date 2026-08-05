"""
Dagster Definitions entry point for the Spartan Judicial campaign data platform.

Run the Dagster UI with:
    dagster dev -m orchestration.dagster_project.definitions

See docs/orchestration.md for the full asset graph and run instructions.
"""

from dagster import Definitions, load_assets_from_modules

from orchestration.dagster_project import assets
from orchestration.dagster_project.jobs import spartan_pipeline_job

all_assets = load_assets_from_modules([assets])

defs = Definitions(
    assets=all_assets,
    jobs=[spartan_pipeline_job],
)
