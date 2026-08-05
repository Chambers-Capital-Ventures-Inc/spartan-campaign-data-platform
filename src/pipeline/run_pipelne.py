"""
Run the Spartan Judicial target-three data pipeline end to end.

This script provides a lightweight orchestration layer for Phase 4.

It runs the current pipeline in sequence:

1. Clean the raw target-three campaign dossier into a silver table.
2. Validate the cleaned silver dossier with Pydantic.
3. Build gold candidate dossier, readiness, and risk-signal outputs.
4. Validate gold outputs.
5. Generate the target-three evaluation report.

This is intentionally simpler than Prefect or Dagster for now. The goal is to
make the prototype repeatable with one command before adding heavier
orchestration tooling.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PIPELINE_STEPS = [
    {
        "name": "Clean target-three dossier",
        "command": ["python", "src/transformations/clean_target_3_dossier.py"],
    },
    {
        "name": "Validate silver target-three dossier",
        "command": ["python", "src/validation/validate_target_3_dossier.py"],
    },
    {
        "name": "Build gold outputs",
        "command": ["python", "src/evaluation/build_gold_outputs.py"],
    },
    {
        "name": "Validate gold outputs",
        "command": ["python", "src/validation/validate_gold_outputs.py"],
    },
    {
        "name": "Generate evaluation report",
        "command": ["python", "src/evaluation/generate_evaluation_report.py"],
    },
]


def generate_run_id() -> str:
    """
    Generate a timestamp-based run ID for the pipeline execution.

    The run ID makes each pipeline execution traceable in logs.
    """
    return datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def run_step(step_name: str, command: list[str], run_id: str) -> None:
    """
    Run one pipeline step and stop execution if the step fails.

    Args:
        step_name: Human-readable step name.
        command: Command to execute.
        run_id: Pipeline run identifier.
    """
    print(f"\n[{run_id}] START: {step_name}")
    print(f"[{run_id}] COMMAND: {' '.join(command)}")

    result = subprocess.run(command, check=False)

    if result.returncode != 0:
        print(f"[{run_id}] FAILED: {step_name}")
        raise RuntimeError(
            f"Step failed with exit code {result.returncode}: {step_name}"
        )

    print(f"[{run_id}] SUCCESS: {step_name}")


def write_pipeline_log(run_id: str, status: str, error: str | None = None) -> None:
    """
    Write a lightweight pipeline log file for the run.

    Args:
        run_id: Pipeline run identifier.
        status: Final pipeline status.
        error: Optional error message if the pipeline failed.
    """
    log_dir = Path("reports/pipeline_runs")
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / f"{run_id}.txt"

    lines = [
        f"run_id: {run_id}",
        f"status: {status}",
        f"timestamp_utc: {datetime.now(timezone.utc).isoformat()}",
    ]

    if error:
        lines.append(f"error: {error}")

    log_path.write_text("\n".join(lines), encoding="utf-8")

    latest_path = log_dir / "latest.txt"
    latest_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """
    Execute the full target-three pipeline.

    Run from the project root:

        python src/pipeline/run_pipeline.py
    """
    run_id = generate_run_id()

    print(f"\nStarting Spartan Judicial pipeline: {run_id}")

    try:
        for step in PIPELINE_STEPS:
            run_step(step["name"], step["command"], run_id)

        write_pipeline_log(run_id=run_id, status="passed")

        print(f"\n[{run_id}] PIPELINE COMPLETE: passed")

    except Exception as exc:
        write_pipeline_log(run_id=run_id, status="failed", error=str(exc))
        print(f"\n[{run_id}] PIPELINE COMPLETE: failed")
        print(f"[{run_id}] ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()