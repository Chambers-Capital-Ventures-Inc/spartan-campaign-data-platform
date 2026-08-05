"""
Run the SQL staging + mart transformation layer over the DuckDB warehouse.

This is a lightweight, dbt-style transformation layer built directly on
DuckDB SQL files. It does NOT replace or modify the existing Python
gold-output pipeline (src/evaluation/build_gold_outputs.py and friends) —
it reads the gold_* DuckDB views that build_duckdb.py already creates over
the Parquet lakehouse layer, and builds readable SQL staging + mart models
on top of them.

Order of operations:
    1. Run staging models (sql/staging/*.sql) — a light cleaning/typing
       pass over the existing gold_* DuckDB views.
    2. Run mart models (sql/marts/*.sql) — candidate-facing and
       source-quality outputs built on top of the staging models.
    3. Export each mart view to Parquet under data/lake/gold/sql_marts/
       and to CSV under data/gold/sql_marts/.

Run from the project root, after export_lakehouse_layers.py and
build_duckdb.py have populated the warehouse:
    python src/storage/run_sql_models.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE_PATH = REPO_ROOT / "data" / "warehouse" / "spartan_campaign.duckdb"

SQL_STAGING_DIR = REPO_ROOT / "sql" / "staging"
SQL_MARTS_DIR = REPO_ROOT / "sql" / "marts"

LAKE_GOLD_SQL_MARTS_DIR = REPO_ROOT / "data" / "lake" / "gold" / "sql_marts"
GOLD_SQL_MARTS_DIR = REPO_ROOT / "data" / "gold" / "sql_marts"

# Explicit run order. Staging models must run before mart models, since the
# marts SELECT FROM the staging views rather than the raw gold_* views.
STAGING_MODELS = [
    "stg_candidate_dossiers.sql",
    "stg_campaign_readiness.sql",
    "stg_risk_signals.sql",
]

MART_MODELS = [
    "mart_candidate_profiles.sql",
    "mart_source_quality.sql",
    "mart_candidate_context.sql",
]

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("run_sql_models")


def connect() -> duckdb.DuckDBPyConnection:
    """Connect to the existing DuckDB warehouse file.

    Does not create the warehouse itself — build_duckdb.py is responsible
    for that, and for creating the bronze/silver/gold views this script's
    staging models read from.
    """
    if not WAREHOUSE_PATH.exists():
        raise FileNotFoundError(
            f"DuckDB warehouse not found at {WAREHOUSE_PATH.relative_to(REPO_ROOT)}. "
            "Run export_lakehouse_layers.py and build_duckdb.py first."
        )
    logger.info("Connecting to DuckDB warehouse: %s", WAREHOUSE_PATH.relative_to(REPO_ROOT))
    return duckdb.connect(str(WAREHOUSE_PATH))


def run_sql_file(conn: duckdb.DuckDBPyConnection, sql_path: Path) -> None:
    """Execute one .sql model file (a CREATE OR REPLACE VIEW statement) against the warehouse."""
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL model file not found: {sql_path.relative_to(REPO_ROOT)}")
    sql_text = sql_path.read_text(encoding="utf-8")
    logger.info("Running model: %s", sql_path.relative_to(REPO_ROOT))
    conn.execute(sql_text)


def run_staging_models(conn: duckdb.DuckDBPyConnection) -> None:
    """Run every staging model, in dependency order, ahead of the marts."""
    logger.info("Running staging models (%d)", len(STAGING_MODELS))
    for filename in STAGING_MODELS:
        run_sql_file(conn, SQL_STAGING_DIR / filename)


def run_mart_models(conn: duckdb.DuckDBPyConnection) -> None:
    """Run every mart model, in dependency order, after the staging models exist."""
    logger.info("Running mart models (%d)", len(MART_MODELS))
    for filename in MART_MODELS:
        run_sql_file(conn, SQL_MARTS_DIR / filename)


def print_mart_row_counts(conn: duckdb.DuckDBPyConnection) -> None:
    """Run a simple row-count query check against each mart model and log the result."""
    logger.info("Mart row counts:")
    for mart_filename in MART_MODELS:
        mart_name = Path(mart_filename).stem
        count = conn.execute(f"SELECT COUNT(*) FROM {mart_name}").fetchone()[0]
        logger.info("  %-30s %d rows", mart_name, count)


def export_mart_outputs(conn: duckdb.DuckDBPyConnection) -> None:
    """Export each mart view to Parquet (lakehouse) and CSV (existing gold convention).

    Parquet copies go to data/lake/gold/sql_marts/, matching the Parquet
    lakehouse layer written by export_lakehouse_layers.py. CSV copies go
    to data/gold/sql_marts/, matching the existing CSV gold-output
    convention used by the Python pipeline, so any downstream tool that
    only reads CSV can still pick up the SQL mart outputs.
    """
    LAKE_GOLD_SQL_MARTS_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_SQL_MARTS_DIR.mkdir(parents=True, exist_ok=True)

    for mart_filename in MART_MODELS:
        mart_name = Path(mart_filename).stem  # e.g. "mart_candidate_profiles"

        parquet_path = LAKE_GOLD_SQL_MARTS_DIR / f"{mart_name}.parquet"
        csv_path = GOLD_SQL_MARTS_DIR / f"{mart_name}.csv"

        conn.execute(
            f"COPY (SELECT * FROM {mart_name}) TO '{parquet_path.as_posix()}' (FORMAT PARQUET)"
        )
        logger.info("Exported %s -> %s", mart_name, parquet_path.relative_to(REPO_ROOT))

        conn.execute(
            f"COPY (SELECT * FROM {mart_name}) TO '{csv_path.as_posix()}' (FORMAT CSV, HEADER)"
        )
        logger.info("Exported %s -> %s", mart_name, csv_path.relative_to(REPO_ROOT))


def main() -> None:
    """Run the full staging -> mart SQL transformation layer and export the mart outputs."""
    conn = connect()
    try:
        run_staging_models(conn)
        run_mart_models(conn)
        print_mart_row_counts(conn)
        export_mart_outputs(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
