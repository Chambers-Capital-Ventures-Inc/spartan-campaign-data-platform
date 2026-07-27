from pathlib import Path
import pandas as pd
from pydantic import ValidationError
from src.schemas.candidate_dossier import CandidateDossier

INPUT_PATH = Path("data/silver/target_3_campaign_dossier_clean.csv")
REPORT_DIR = Path("reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = REPORT_DIR / "target_3_validation_report.csv"

def main():
    df = pd.read_csv(INPUT_PATH, dtype={"filer_id": str})
    results = []

    for idx, row in df.iterrows():
        record = row.where(pd.notnull(row), None).to_dict()

        try:
            CandidateDossier(**record)
            results.append({
                "row_number": idx + 1,
                "candidate_name": record.get("candidate_name"),
                "validation_status": "passed",
                "error": "",
            })
        except ValidationError as e:
            results.append({
                "row_number": idx + 1,
                "candidate_name": record.get("candidate_name"),
                "validation_status": "failed",
                "error": str(e),
            })

    report = pd.DataFrame(results)
    report.to_csv(REPORT_PATH, index=False)
    print(f"Wrote validation report to {REPORT_PATH}")
    print(report)

if __name__ == "__main__":
    main()