from pathlib import Path
import pandas as pd
from datetime import datetime, timezone

BRONZE_PATH = Path("data/bronze/target_3_campaign_dossier_raw.csv")
SILVER_DIR = Path("data/silver")
SILVER_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = SILVER_DIR / "target_3_campaign_dossier_clean.csv"

EXPECTED_COLUMNS = [
    "candidate_name",
    "party",
    "court_name",
    "court_type",
    "incumbent_status",
    "state_bar_profile_url",
    "bar_number",
    "bar_status",
    "licensed_since",
    "public_discipline_flag",
    "campaign_finance_source",
    "campaign_finance_url",
    "filer_id",
    "total_contributions",
    "total_expenditures",
    "oca_case_category",
    "active_pending_total",
    "long_pending_count",
    "long_pending_threshold",
    "long_pending_pct",
    "scjc_checked",
    "scjc_result",
    "overall_confidence",
    "missing_fields",
    "notes",
]

def clean_money(value):
    if pd.isna(value) or str(value).strip() == "":
        return pd.NA
    return str(value).strip().replace(",", "").replace("$", "")

def clean_text(value):
    if pd.isna(value):
        return pd.NA
    cleaned = str(value).strip()
    return cleaned if cleaned else pd.NA

def main():
    df = pd.read_csv(BRONZE_PATH, dtype=str)

    # Drop completely empty columns and rows.
    df = df.dropna(axis=1, how="all")
    df = df.dropna(how="all")

    # Strip whitespace from column names.
    df.columns = [c.strip() for c in df.columns]

    # Keep expected columns only, in expected order.
    missing_cols = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing expected columns: {missing_cols}")

    df = df[EXPECTED_COLUMNS].copy()

    # Strip leading/trailing whitespace from all text cells.
    for col in df.columns:
        df[col] = df[col].map(clean_text)

    # Preserve filer_id as text with leading zeros.
    df["filer_id"] = df["filer_id"].map(lambda x: clean_text(x))

    # Clean money fields.
    df["total_contributions"] = df["total_contributions"].map(clean_money)
    df["total_expenditures"] = df["total_expenditures"].map(clean_money)

    # Convert numeric fields safely.
    numeric_cols = [
        "total_contributions",
        "total_expenditures",
        "active_pending_total",
        "long_pending_count",
        "long_pending_pct",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Standardize common status values.
    df["public_discipline_flag"] = df["public_discipline_flag"].replace({
        " No": "No",
        "no": "No",
        "YES": "Yes",
        "yes": "Yes",
    })

    df["scjc_checked"] = df["scjc_checked"].replace({
        "yes": "Yes",
        "YES": "Yes",
        "no": "No",
    })

    df["overall_confidence"] = df["overall_confidence"].replace({
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    })

    # Add ingestion metadata.
    df["source_id"] = "SRC003"
    df["ingested_at"] = datetime.now(timezone.utc).isoformat()
    df["verification_status"] = "Prototype complete"
    df["source_caveat"] = (
        "Derived dossier file. OCA metrics are court-level context; "
        "TEC values are report-period totals; SCJC results are source-scoped."
    )

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote cleaned dossier to {OUTPUT_PATH}")
    print(df)

if __name__ == "__main__":
    main()