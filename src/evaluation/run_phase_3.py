"""
Run the full Phase 3 gold/evaluation workflow.

This script is a lightweight orchestration runner. It does not use Prefect or
Dagster yet. It simply executes the Phase 3 steps in the correct order:

1. Build gold outputs.
2. Validate gold outputs.
3. Generate the target three-campaign evaluation report.

This gives the project an early version of repeatable orchestration before
the formal Phase 4 pipeline work begins.
"""

import subprocess
import sys


COMMANDS = [
    ["python", "src/evaluation/build_gold_outputs.py"],
    ["python", "src/validation/validate_gold_outputs.py"],
    ["python", "src/evaluation/generate_evaluation_report.py"],
]


def run_command(command: list[str]) -> None:
    """
    Run one command and stop the pipeline if it fails.
    """
    print(f"\nRunning: {' '.join(command)}")

    result = subprocess.run(command, check=False)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}"
        )


def main() -> None:
    """
    Execute all Phase 3 scripts in sequence.

    This should be run from the project root.
    """
    try:
        for command in COMMANDS:
            run_command(command)

        print("\nPhase 3 workflow completed successfully.")

    except Exception as exc:
        print(f"\nPhase 3 workflow failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()