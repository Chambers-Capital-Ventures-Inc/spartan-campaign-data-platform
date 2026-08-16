"""
Build a local DuckDB warehouse over the Parquet lakehouse layer.

This script requires no cloud credentials. It connects to a local DuckDB
file at data/warehouse/spartan_campaign.duckdb and creates views directly
over the Parquet files written by export_lakehouse_layers.py, so the
warehouse always reflects the latest exported Parquet data without copying
it into DuckDB's own storage format.

Run from the project root, after export_lakehouse_layers.py:
    python src/storage/build_duckdb.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
LAKE_ROOT = REPO_ROOT / "data" / "lake"
WAREHOUSE_DIR = REPO_ROOT / "data" / "warehouse"
WAREHOUSE_PATH = WAREHOUSE_DIR / "spartan_campaign.duckdb"

# Maps each warehouse view name to the Parquet file that backs it.
VIEW_SOURCE_FILES: dict[str, Path] = {
    "bronze_target_3_dossier": LAKE_ROOT / "bronze" / "target_3_campaign_dossier_raw.parquet",
    "silver_target_3_dossier": LAKE_ROOT / "silver" / "target_3_campaign_dossier_clean.parquet",
    "gold_candidate_dossiers": LAKE_ROOT / "gold" / "gold_candidate_dossiers.parquet",
    "gold_campaign_readiness": LAKE_ROOT / "gold" / "gold_campaign_readiness.parquet",
    "gold_risk_signals": LAKE_ROOT / "gold" / "gold_risk_signals.parquet",
}

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("build_duckdb")


def ensure_warehouse_directory() -> None:
    """Create the data/warehouse directory if it does not already exist."""
    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)


def connect() -> duckdb.DuckDBPyConnection:
    """Open (creating if needed) the local DuckDB warehouse file."""
    ensure_warehouse_directory()
    logger.info("Connecting to DuckDB warehouse: %s", WAREHOUSE_PATH.relative_to(REPO_ROOT))
    return duckdb.connect(str(WAREHOUSE_PATH))


def create_view(conn: duckdb.DuckDBPyConnection, view_name: str, parquet_path: Path) -> bool:
    """Create or replace one DuckDB view over a Parquet file.

    Returns True if the view was created, False if the source Parquet file
    was missing, in which case the view is skipped rather than failing the
    whole run.
    """
    if not parquet_path.exists():
        logger.warning(
            "Skipping view %s: Parquet file not found at %s. Run "
            "export_lakehouse_layers.py first.",
            view_name,
            parquet_path.relative_to(REPO_ROOT),
        )
        return False

    conn.execute(
        f"CREATE OR REPLACE VIEW {view_name} AS "
        f"SELECT * FROM read_parquet('{parquet_path.as_posix()}')"
    )
    logger.info("Created view %s -> %s", view_name, parquet_path.relative_to(REPO_ROOT))
    return True


def create_all_views(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Create every configured warehouse view, skipping missing Parquet sources.

    Returns the list of view names that were successfully created.
    """
    created = []
    for view_name, parquet_path in VIEW_SOURCE_FILES.items():
        if create_view(conn, view_name, parquet_path):
            created.append(view_name)
    return created


def print_row_counts(conn: duckdb.DuckDBPyConnection, view_names: list[str]) -> None:
    """Run a simple row-count query check against each view and log the result."""
    logger.info("Running row-count check against %d view(s):", len(view_names))
    for view_name in view_names:
        count = conn.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()[0]
        logger.info("  %-30s %d rows", view_name, count)


def main() -> None:
    """Build the DuckDB warehouse views and print a row-count sanity check."""
    conn = connect()
    try:
        view_names = create_all_views(conn)
        if not view_names:
            logger.warning("No views were created. Have you run export_lakehouse_layers.py?")
            return
        print_row_counts(conn, view_names)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
