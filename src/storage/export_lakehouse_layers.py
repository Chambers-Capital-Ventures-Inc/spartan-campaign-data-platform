"""
Export the Spartan Judicial CSV data layers into a Parquet-based lakehouse.

This script does NOT replace the existing CSV pipeline (src/pipeline/run_pipelne.py
and friends). It reads the current bronze, silver, and gold CSV outputs and
re-exports them as Parquet files under data/lake/, plus a full point-in-time
snapshot copy under data/lake/snapshots/run_id=<run_id>/. This gives the
project a columnar, typed, run-tracked storage layer on top of the existing
CSV workflow, without touching that workflow.

Run from the project root:
    python src/storage/export_lakehouse_layers.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_BRONZE = REPO_ROOT / "data" / "bronze"
DATA_SILVER = REPO_ROOT / "data" / "silver"
DATA_GOLD = REPO_ROOT / "data" / "gold"

LAKE_ROOT = REPO_ROOT / "data" / "lake"
LAKE_BRONZE = LAKE_ROOT / "bronze"
LAKE_SILVER = LAKE_ROOT / "silver"
LAKE_GOLD = LAKE_ROOT / "gold"
LAKE_SEMANTIC = LAKE_ROOT / "semantic"
LAKE_SNAPSHOTS = LAKE_ROOT / "snapshots"

# Identifier-like columns that must stay text so leading zeros survive
# Parquet round-tripping (e.g. TEC filer IDs, State Bar numbers).
STRING_ID_COLUMNS = {"filer_id", "bar_number", "source_id"}

# Maps each lakehouse layer to the existing CSV files that currently back it.
LAYER_SOURCE_FILES: dict[str, list[Path]] = {
    "bronze": [DATA_BRONZE / "target_3_campaign_dossier_raw.csv"],
    "silver": [DATA_SILVER / "target_3_campaign_dossier_clean.csv"],
    "gold": [
        DATA_GOLD / "gold_candidate_dossiers.csv",
        DATA_GOLD / "gold_campaign_readiness.csv",
        DATA_GOLD / "gold_risk_signals.csv",
    ],
}

LAYER_TARGET_DIRS: dict[str, Path] = {
    "bronze": LAKE_BRONZE,
    "silver": LAKE_SILVER,
    "gold": LAKE_GOLD,
}

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("export_lakehouse_layers")


def generate_run_id() -> str:
    """Generate a timestamp-based run ID, matching the CSV pipeline's run_id format."""
    return datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def ensure_lake_directories() -> None:
    """Create the lakehouse folder structure if it does not already exist."""
    for directory in (LAKE_BRONZE, LAKE_SILVER, LAKE_GOLD, LAKE_SEMANTIC, LAKE_SNAPSHOTS):
        directory.mkdir(parents=True, exist_ok=True)
        logger.info("Ensured directory exists: %s", directory.relative_to(REPO_ROOT))


def load_csv_with_string_ids(csv_path: Path) -> pd.DataFrame:
    """Read a CSV file, forcing identifier-like columns to stay string typed.

    Only applies the string override to columns that are actually present in
    the file's header, so this works across bronze/silver/gold files that
    have different schemas.
    """
    header = pd.read_csv(csv_path, nrows=0).columns
    dtype_overrides = {col: str for col in header if col in STRING_ID_COLUMNS}
    return pd.read_csv(csv_path, dtype=dtype_overrides)


def add_lineage_columns(df: pd.DataFrame, run_id: str, exported_at: str) -> pd.DataFrame:
    """Return a copy of df with run_id and exported_at lineage columns appended."""
    enriched = df.copy()
    enriched["run_id"] = run_id
    enriched["exported_at"] = exported_at
    return enriched


def export_csv_to_parquet(
    csv_path: Path, layer_dir: Path, run_id: str, exported_at: str
) -> tuple[Path, pd.DataFrame] | None:
    """Read one CSV file and write it out as a Parquet file with lineage columns.

    Returns a (output_path, dataframe) tuple for the file written into the
    current lakehouse layer directory, or None if the source CSV is missing.
    """
    if not csv_path.exists():
        logger.warning("Skipping missing source CSV: %s", csv_path.relative_to(REPO_ROOT))
        return None

    df = load_csv_with_string_ids(csv_path)
    df = add_lineage_columns(df, run_id, exported_at)

    output_path = layer_dir / f"{csv_path.stem}.parquet"
    df.to_parquet(output_path, index=False)
    logger.info("Wrote %d rows -> %s", len(df), output_path.relative_to(REPO_ROOT))
    return output_path, df


def write_snapshot_copy(df: pd.DataFrame, layer: str, csv_path: Path, run_id: str) -> Path:
    """Write a point-in-time snapshot copy of one exported table.

    Snapshots live under data/lake/snapshots/run_id=<run_id>/<layer>/ so a
    given run's full set of tables can always be reconstructed later.
    """
    snapshot_dir = LAKE_SNAPSHOTS / f"run_id={run_id}" / layer
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"{csv_path.stem}.parquet"
    df.to_parquet(snapshot_path, index=False)
    logger.info("Wrote snapshot -> %s", snapshot_path.relative_to(REPO_ROOT))
    return snapshot_path


def export_all_layers(run_id: str | None = None) -> str:
    """Export bronze, silver, and gold CSV files into the Parquet lakehouse layer.

    Also writes a full point-in-time snapshot for this run under
    data/lake/snapshots/run_id=<run_id>/. Existing CSV files are only read,
    never modified or deleted.

    Returns the run_id used for this export.
    """
    run_id = run_id or generate_run_id()
    exported_at = datetime.now(timezone.utc).isoformat()

    logger.info("Starting lakehouse export: run_id=%s", run_id)
    ensure_lake_directories()

    for layer, csv_paths in LAYER_SOURCE_FILES.items():
        layer_dir = LAYER_TARGET_DIRS[layer]
        for csv_path in csv_paths:
            result = export_csv_to_parquet(csv_path, layer_dir, run_id, exported_at)
            if result is None:
                continue
            _, df = result
            write_snapshot_copy(df, layer, csv_path, run_id)

    logger.info("Lakehouse export complete: run_id=%s", run_id)
    return run_id


def main() -> None:
    """Run the lakehouse export as a standalone script."""
    export_all_layers()


if __name__ == "__main__":
    main()
