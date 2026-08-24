"""
Export the Spartan Judicial gold/mart data into a Postgres/Supabase serving layer.

This is the first step toward the candidate lookup frontend eventually
reading from a real database instead of local CSV files. It builds six
serving tables (see sql/postgres/create_serving_tables.sql) and upserts
them into Postgres:

    candidate_profiles
    candidate_profile_completeness
    candidate_context_notes
    source_quality
    pipeline_runs
    semantic_candidate_summaries

Data source preference, per table: the DuckDB warehouse
(data/warehouse/spartan_campaign.duckdb, built by
src/storage/build_duckdb.py + src/storage/run_sql_models.py) if it exists,
otherwise the data/gold/*.csv files. Either way, filer_id and source_id are
always kept as text so leading zeros are preserved.

This script does not change the Streamlit app, which keeps reading the
local CSV files for now (see docs/serving_layer.md).

Usage:
    # Preview the six serving tables without connecting to a database:
    python src/storage/export_to_postgres.py --dry-run

    # Apply the schema (idempotent) and upsert into Postgres/Supabase:
    DATABASE_URL=postgresql://user:password@host:5432/dbname \\
        python src/storage/export_to_postgres.py
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert
from dotenv import load_dotenv



# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# src/storage/export_to_postgres.py -> repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_GOLD = REPO_ROOT / "data" / "gold"
GOLD_DOSSIERS_CSV = DATA_GOLD / "gold_candidate_dossiers.csv"
GOLD_READINESS_CSV = DATA_GOLD / "gold_campaign_readiness.csv"
GOLD_RISK_SIGNALS_CSV = DATA_GOLD / "gold_risk_signals.csv"

WAREHOUSE_PATH = REPO_ROOT / "data" / "warehouse" / "spartan_campaign.duckdb"
PIPELINE_RUNS_DIR = REPO_ROOT / "reports" / "pipeline_runs"
SCHEMA_SQL_PATH = REPO_ROOT / "sql" / "postgres" / "create_serving_tables.sql"

PARTY_LABELS = {"R": "Republican", "D": "Democratic", "I": "Independent"}

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("export_to_postgres")


# ---------------------------------------------------------------------------
# SQLAlchemy Core table metadata
#
# These mirror sql/postgres/create_serving_tables.sql exactly. They are
# used only to build INSERT ... ON CONFLICT DO UPDATE statements below —
# the actual CREATE TABLE statements always come from that SQL file (see
# apply_schema()), so the two stay in sync by construction.
# ---------------------------------------------------------------------------

METADATA = sa.MetaData()

candidate_profiles_table = sa.Table(
    "candidate_profiles",
    METADATA,
    sa.Column("candidate_name", sa.Text, primary_key=True),
    sa.Column("party", sa.Text),
    sa.Column("court_name", sa.Text),
    sa.Column("court_type", sa.Text),
    sa.Column("incumbent_status", sa.Text),
    sa.Column("bar_status", sa.Text),
    sa.Column("licensed_since", sa.Text),
    sa.Column("public_discipline_flag", sa.Text),
    sa.Column("filer_id", sa.Text),
    sa.Column("total_contributions", sa.Numeric),
    sa.Column("total_expenditures", sa.Numeric),
    sa.Column("oca_case_category", sa.Text),
    sa.Column("active_pending_total", sa.Integer),
    sa.Column("long_pending_count", sa.Integer),
    sa.Column("long_pending_threshold", sa.Text),
    sa.Column("long_pending_pct", sa.Float),
    sa.Column("scjc_result", sa.Text),
    sa.Column("overall_confidence", sa.Text),
    sa.Column("source_caveat", sa.Text),
    sa.Column("notes", sa.Text),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

candidate_profile_completeness_table = sa.Table(
    "candidate_profile_completeness",
    METADATA,
    sa.Column("candidate_name", sa.Text, primary_key=True),
    sa.Column("court_name", sa.Text),
    sa.Column("incumbent_status", sa.Text),
    sa.Column("readiness_score", sa.Float),
    sa.Column("readiness_label", sa.Text),
    sa.Column("fields_complete", sa.Integer),
    sa.Column("fields_possible", sa.Integer),
    sa.Column("missing_or_review_fields", sa.Text),
    sa.Column("overall_confidence", sa.Text),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

candidate_context_notes_table = sa.Table(
    "candidate_context_notes",
    METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("candidate_name", sa.Text, nullable=False),
    sa.Column("risk_type", sa.Text, nullable=False),
    sa.Column("risk_level", sa.Text),
    sa.Column("risk_message", sa.Text),
    sa.Column("source_id", sa.Text),
    sa.Column("recommended_action", sa.Text),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

source_quality_table = sa.Table(
    "source_quality",
    METADATA,
    sa.Column("source_id", sa.Text, primary_key=True),
    sa.Column("total_context_notes", sa.Integer),
    sa.Column("high_severity_notes", sa.Integer),
    sa.Column("medium_severity_notes", sa.Integer),
    sa.Column("low_severity_notes", sa.Integer),
    sa.Column("candidates_referencing_source", sa.Integer),
    sa.Column("distinct_context_types", sa.Text),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

pipeline_runs_table = sa.Table(
    "pipeline_runs",
    METADATA,
    sa.Column("run_id", sa.Text, primary_key=True),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("timestamp_utc", sa.Text),
    sa.Column("error", sa.Text),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

semantic_candidate_summaries_table = sa.Table(
    "semantic_candidate_summaries",
    METADATA,
    sa.Column("candidate_name", sa.Text, primary_key=True),
    sa.Column("profile_summary", sa.Text),
    sa.Column("finance_summary", sa.Text),
    sa.Column("court_context_summary", sa.Text),
    sa.Column("generated_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

# (table name, SQLAlchemy Table, upsert conflict/key columns, columns to
# leave untouched on conflict). Order matters: tables with a foreign key
# to candidate_profiles must be written after it.
TABLE_WRITE_ORDER: list[tuple[str, sa.Table, list[str], set[str]]] = [
    ("candidate_profiles", candidate_profiles_table, ["candidate_name"], set()),
    ("candidate_profile_completeness", candidate_profile_completeness_table, ["candidate_name"], set()),
    ("candidate_context_notes", candidate_context_notes_table, ["candidate_name", "risk_type"], set()),
    ("source_quality", source_quality_table, ["source_id"], set()),
    ("pipeline_runs", pipeline_runs_table, ["run_id"], set()),
    ("semantic_candidate_summaries", semantic_candidate_summaries_table, ["candidate_name"], {"generated_at"}),
]


# ---------------------------------------------------------------------------
# Source data loading (DuckDB marts, falling back to data/gold CSVs)
# ---------------------------------------------------------------------------

def _duckdb_warehouse_available() -> bool:
    """Return True if the local DuckDB warehouse file exists on disk."""
    return WAREHOUSE_PATH.exists()


def _query_duckdb(sql: str) -> pd.DataFrame:
    """Run one read-only query against the local DuckDB warehouse and return a DataFrame."""
    import duckdb  # imported lazily: only needed when the warehouse actually exists

    conn = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    try:
        return conn.execute(sql).fetchdf()
    finally:
        conn.close()


def load_candidate_dossiers() -> pd.DataFrame:
    """Load candidate dossier rows from the DuckDB gold view, or the gold CSV as a fallback."""
    if _duckdb_warehouse_available():
        logger.info("Reading candidate dossiers from DuckDB view gold_candidate_dossiers")
        return _query_duckdb("SELECT * FROM gold_candidate_dossiers")
    logger.info(
        "DuckDB warehouse not found; reading candidate dossiers from %s",
        GOLD_DOSSIERS_CSV.relative_to(REPO_ROOT),
    )
    return pd.read_csv(GOLD_DOSSIERS_CSV, dtype={"filer_id": str})


def load_campaign_readiness() -> pd.DataFrame:
    """Load profile-completeness rows from the DuckDB gold view, or the gold CSV as a fallback."""
    if _duckdb_warehouse_available():
        logger.info("Reading campaign readiness from DuckDB view gold_campaign_readiness")
        return _query_duckdb("SELECT * FROM gold_campaign_readiness")
    logger.info(
        "DuckDB warehouse not found; reading campaign readiness from %s",
        GOLD_READINESS_CSV.relative_to(REPO_ROOT),
    )
    return pd.read_csv(GOLD_READINESS_CSV)


def load_risk_signals() -> pd.DataFrame:
    """Load raw risk-signal/context-note rows from the DuckDB gold view, or the gold CSV as a fallback."""
    if _duckdb_warehouse_available():
        logger.info("Reading risk signals from DuckDB view gold_risk_signals")
        return _query_duckdb("SELECT * FROM gold_risk_signals")
    logger.info(
        "DuckDB warehouse not found; reading risk signals from %s",
        GOLD_RISK_SIGNALS_CSV.relative_to(REPO_ROOT),
    )
    return pd.read_csv(GOLD_RISK_SIGNALS_CSV, dtype={"source_id": str})


def _aggregate_source_quality(risk_df: pd.DataFrame) -> pd.DataFrame:
    """Pandas equivalent of sql/marts/mart_source_quality.sql.

    Used only when the DuckDB mart isn't available, so the CSV-only
    fallback path still produces a source-quality rollup.
    """
    records = []
    for source_id, group in risk_df.groupby("source_id"):
        records.append(
            {
                "source_id": source_id,
                "total_context_notes": len(group),
                "high_severity_notes": int((group["risk_level"] == "High").sum()),
                "medium_severity_notes": int((group["risk_level"] == "Medium").sum()),
                "low_severity_notes": int((group["risk_level"] == "Low").sum()),
                "candidates_referencing_source": int(group["candidate_name"].nunique()),
                "distinct_context_types": ", ".join(sorted(group["risk_type"].unique())),
            }
        )
    return pd.DataFrame.from_records(records).sort_values("source_id").reset_index(drop=True)


def load_source_quality(risk_df: pd.DataFrame) -> pd.DataFrame:
    """Load the per-source quality rollup from the DuckDB mart, or compute it from risk_df."""
    if _duckdb_warehouse_available():
        try:
            logger.info("Reading source quality from DuckDB view mart_source_quality")
            return _query_duckdb(
                "SELECT source_id, total_context_notes, high_severity_notes, "
                "medium_severity_notes, low_severity_notes, "
                "candidates_referencing_source, distinct_context_types "
                "FROM mart_source_quality"
            )
        except Exception as exc:  # e.g. mart view not built yet
            logger.warning("mart_source_quality unavailable (%s); computing from risk signals", exc)
    logger.info("Computing source quality from risk-signal rows (pandas fallback)")
    return _aggregate_source_quality(risk_df)


def load_candidate_context_notes(risk_df: pd.DataFrame) -> pd.DataFrame:
    """Load candidate context notes from the DuckDB mart, or select them directly from risk_df."""
    if _duckdb_warehouse_available():
        try:
            logger.info("Reading candidate context notes from DuckDB view mart_candidate_context")
            return _query_duckdb(
                "SELECT candidate_name, risk_type, risk_level, risk_message, "
                "source_id, recommended_action FROM mart_candidate_context"
            )
        except Exception as exc:  # e.g. mart view not built yet
            logger.warning("mart_candidate_context unavailable (%s); using gold risk signals", exc)
    columns = ["candidate_name", "risk_type", "risk_level", "risk_message", "source_id", "recommended_action"]
    return risk_df[columns].copy()


def load_pipeline_runs() -> pd.DataFrame:
    """Parse reports/pipeline_runs/run_*.txt into the pipeline_runs table shape.

    Always reads from these log files regardless of DuckDB/CSV mode: they
    are the authoritative record of when each pipeline run happened and
    whether it passed, and that information doesn't live in the gold
    tables themselves.
    """
    records = []
    if PIPELINE_RUNS_DIR.exists():
        for log_path in sorted(PIPELINE_RUNS_DIR.glob("run_*.txt")):
            fields: dict[str, str] = {}
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()
            records.append(
                {
                    "run_id": fields.get("run_id", log_path.stem),
                    "status": fields.get("status", "unknown"),
                    "timestamp_utc": fields.get("timestamp_utc"),
                    "error": fields.get("error"),
                }
            )
    return pd.DataFrame.from_records(records, columns=["run_id", "status", "timestamp_utc", "error"])


# ---------------------------------------------------------------------------
# Serving-table shaping
# ---------------------------------------------------------------------------

def build_candidate_profiles(dossiers_df: pd.DataFrame) -> pd.DataFrame:
    """Shape raw dossier rows into the candidate_profiles table schema."""
    columns = [
        "candidate_name", "party", "court_name", "court_type", "incumbent_status",
        "bar_status", "licensed_since", "public_discipline_flag", "filer_id",
        "total_contributions", "total_expenditures", "oca_case_category",
        "active_pending_total", "long_pending_count", "long_pending_threshold",
        "long_pending_pct", "scjc_result", "overall_confidence", "source_caveat", "notes",
    ]
    df = dossiers_df[columns].copy()
    df["filer_id"] = df["filer_id"].astype(str)  # preserve leading zeros
    return df


def build_candidate_profile_completeness(readiness_df: pd.DataFrame) -> pd.DataFrame:
    """Shape raw readiness rows into the candidate_profile_completeness table schema."""
    columns = [
        "candidate_name", "court_name", "incumbent_status", "readiness_score",
        "readiness_label", "fields_complete", "fields_possible",
        "missing_or_review_fields", "overall_confidence",
    ]
    return readiness_df[columns].copy()


def build_candidate_context_notes(context_df: pd.DataFrame) -> pd.DataFrame:
    """Shape raw context-note rows into the candidate_context_notes table schema."""
    columns = ["candidate_name", "risk_type", "risk_level", "risk_message", "source_id", "recommended_action"]
    df = context_df[columns].copy()
    df["source_id"] = df["source_id"].astype(str)
    return df


def build_source_quality(source_quality_df: pd.DataFrame) -> pd.DataFrame:
    """Shape the source-quality rollup rows into the source_quality table schema."""
    columns = [
        "source_id", "total_context_notes", "high_severity_notes",
        "medium_severity_notes", "low_severity_notes",
        "candidates_referencing_source", "distinct_context_types",
    ]
    df = source_quality_df[columns].copy()
    df["source_id"] = df["source_id"].astype(str)
    return df


def _profile_summary(row: pd.Series) -> str:
    """Deterministic plain-English profile summary (mirrors the Streamlit app's phrasing)."""
    party_code = str(row.get("party") or "").strip()
    party = PARTY_LABELS.get(party_code, party_code or "an unspecified-party")
    court_name = row.get("court_name") or "an unspecified court"
    name = row.get("candidate_name") or "This candidate"
    return (
        f"{name} is listed in this prototype as a {party} candidate for the "
        f"{court_name}. This profile brings together public professional "
        f"information, a campaign finance snapshot, court-level context for the "
        f"seat, and a public sanctions archive check."
    )


def _finance_summary(row: pd.Series) -> str:
    """Deterministic plain-English campaign finance summary."""
    return (
        "This prototype captured a campaign finance snapshot from the Texas "
        "Ethics Commission records. The contribution and expenditure values "
        "shown here reflect the selected/latest report-period totals captured "
        "in the prototype, not lifetime or full-cycle totals."
    )


def _court_context_summary(row: pd.Series) -> str:
    """Deterministic, number-grounded plain-English court-context summary."""
    case_category = row.get("oca_case_category") or "court"
    active_total = row.get("active_pending_total")
    long_count = row.get("long_pending_count")
    long_pct = row.get("long_pending_pct")

    sentence = (
        "This court-level context describes the court seat associated with the "
        "race. It should not be read as individual candidate performance."
    )

    if pd.notna(active_total) and pd.notna(long_count) and pd.notna(long_pct):
        try:
            sentence = (
                f"According to the court-level dataset used in this prototype, "
                f"{int(float(long_count)):,} of {int(float(active_total)):,} active "
                f"pending {case_category} cases were classified as long-pending, or "
                f"about {float(long_pct) * 100:.1f}%. " + sentence
            )
        except (TypeError, ValueError):
            pass

    incumbent_status = str(row.get("incumbent_status") or "").strip().lower()
    if incumbent_status == "challenger":
        sentence += (
            " Because this candidate is a challenger, current court metrics "
            "describe the seat they are running for, not their personal "
            "judicial record."
        )
    elif incumbent_status == "incumbent":
        sentence += (
            " Because this candidate is an incumbent, the court-level data may "
            "be more directly relevant to the seat they hold, but it still may "
            "reflect staffing, filings, case mix, and broader court-system "
            "conditions."
        )
    return sentence


def build_semantic_candidate_summaries(dossiers_df: pd.DataFrame) -> pd.DataFrame:
    """Build one plain-English narrative row per candidate from the dossier fields.

    Uses the same deterministic template approach as the Streamlit app (no
    LLM, no hardcoded per-candidate text), so this pre-generated copy stays
    consistent with what the frontend already shows.
    """
    records = [
        {
            "candidate_name": row["candidate_name"],
            "profile_summary": _profile_summary(row),
            "finance_summary": _finance_summary(row),
            "court_context_summary": _court_context_summary(row),
        }
        for _, row in dossiers_df.iterrows()
    ]
    return pd.DataFrame.from_records(records, columns=["candidate_name", "profile_summary", "finance_summary", "court_context_summary"])


def build_serving_tables() -> dict[str, pd.DataFrame]:
    """Load every source table and shape it into the six serving-table DataFrames."""
    dossiers_df = load_candidate_dossiers()
    readiness_df = load_campaign_readiness()
    risk_df = load_risk_signals()

    source_quality_raw = load_source_quality(risk_df)
    context_notes_raw = load_candidate_context_notes(risk_df)

    return {
        "candidate_profiles": build_candidate_profiles(dossiers_df),
        "candidate_profile_completeness": build_candidate_profile_completeness(readiness_df),
        "candidate_context_notes": build_candidate_context_notes(context_notes_raw),
        "source_quality": build_source_quality(source_quality_raw),
        "pipeline_runs": load_pipeline_runs(),
        "semantic_candidate_summaries": build_semantic_candidate_summaries(dossiers_df),
    }


# ---------------------------------------------------------------------------
# Postgres write path
# ---------------------------------------------------------------------------

def _records_with_nulls(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to a list of dicts with NaN replaced by None.

    Done per-value (not via DataFrame.where) because pandas keeps an
    all-empty column as float64 and silently turns an assigned None back
    into NaN when the column dtype is numeric.
    """
    records = df.to_dict(orient="records")
    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and pd.isna(value):
                record[key] = None
    return records


def apply_schema(engine: sa.engine.Engine) -> None:
    """Apply sql/postgres/create_serving_tables.sql against the target database.

    Every statement in that file is CREATE TABLE IF NOT EXISTS, so running
    this on every export is safe: it only creates tables that don't exist
    yet and never touches existing data.
    """
    sql_text = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    logger.info("Applying schema from %s", SCHEMA_SQL_PATH.relative_to(REPO_ROOT))
    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        cursor.execute(sql_text)
        raw_conn.commit()
        cursor.close()
    finally:
        raw_conn.close()


def upsert_dataframe(
    engine: sa.engine.Engine,
    table: sa.Table,
    df: pd.DataFrame,
    conflict_columns: list[str],
    preserve_on_conflict: set[str] = frozenset(),
) -> int:
    """Upsert every row of df into table, keyed on conflict_columns.

    Uses PostgreSQL's INSERT ... ON CONFLICT DO UPDATE so re-running the
    export is idempotent: existing rows are refreshed in place instead of
    duplicated. Columns named in preserve_on_conflict (e.g. a
    first-generated timestamp) are set on insert but left untouched when a
    row already exists.
    """
    if df.empty:
        return 0

    table_columns = set(table.columns.keys())
    records = [
        {key: value for key, value in record.items() if key in table_columns}
        for record in _records_with_nulls(df)
    ]

    insert_stmt = pg_insert(table).values(records)
    update_columns = {
        column.name: insert_stmt.excluded[column.name]
        for column in table.columns
        if column.name not in conflict_columns
        and column.name not in preserve_on_conflict
        and column.name not in ("id", "updated_at")
    }
    if "updated_at" in table_columns:
        update_columns["updated_at"] = sa.func.now()

    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=conflict_columns,
        set_=update_columns,
    )

    with engine.begin() as conn:
        conn.execute(upsert_stmt)

    return len(records)


def write_all_tables(engine: sa.engine.Engine, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Upsert every serving table into Postgres, in foreign-key-safe order."""
    row_counts: dict[str, int] = {}
    for table_name, sa_table, conflict_columns, preserve_columns in TABLE_WRITE_ORDER:
        count = upsert_dataframe(engine, sa_table, tables[table_name], conflict_columns, preserve_columns)
        row_counts[table_name] = count
        logger.info("Upserted %d row(s) into %s", count, table_name)
    return row_counts


def print_dry_run_summary(tables: dict[str, pd.DataFrame]) -> None:
    """Print what would be written to Postgres, without connecting to a database."""
    print("\n[DRY RUN] No database connection was made. Preview of the serving tables:\n")
    for table_name, _, conflict_columns, _ in TABLE_WRITE_ORDER:
        df = tables[table_name]
        print(f"- {table_name}: {len(df)} row(s), upsert key = {conflict_columns}")
        print(f"  columns: {list(df.columns)}")
        if not df.empty:
            print(f"  sample row: {df.iloc[0].to_dict()}")
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Build the serving tables and either preview them (--dry-run) or upsert them into Postgres."""
    parser = argparse.ArgumentParser(
        description="Export the Spartan Judicial gold/mart data into the Postgres/Supabase serving tables."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the serving tables in memory and print a summary without connecting to a database.",
    )
    args = parser.parse_args()

    logger.info("Building serving tables (DuckDB marts if available, else data/gold CSVs)")
    tables = build_serving_tables()

    if args.dry_run:
        print_dry_run_summary(tables)
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error(
            "DATABASE_URL is not set. Set it to your Postgres/Supabase connection string "
            "(e.g. postgresql://user:password@host:5432/dbname), or re-run with --dry-run "
            "to preview the export without a database. See docs/serving_layer.md."
        )
        raise SystemExit(1)

    engine = sa.create_engine(database_url)
    try:
        apply_schema(engine)
        row_counts = write_all_tables(engine, tables)
        logger.info("Export complete: %s", row_counts)
    except sa.exc.SQLAlchemyError as exc:
        logger.error("Failed to write to Postgres: %s", exc)
        raise SystemExit(1) from exc
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()