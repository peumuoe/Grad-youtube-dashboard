from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

PIPELINE_SCRIPTS = [
    "scripts/13_import_provided_scripts.py",
    "scripts/03_collect_transcripts_stub.py",
    "scripts/04_prepare_transcript_review.py",
]


def run_one(script_path: str) -> None:
    """Run one pipeline script and stop immediately on failure."""
    completed = subprocess.run(
        [str(PYTHON_EXE), script_path],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(f"Pipeline stopped because {script_path} failed with code {completed.returncode}")


def main() -> None:
    if not PYTHON_EXE.exists():
        raise FileNotFoundError(f"Python executable was not found: {PYTHON_EXE}")

    for script_path in PIPELINE_SCRIPTS:
        print(f"Running {script_path} ...")
        run_one(script_path)

    print("Original text sync pipeline completed.")


if __name__ == "__main__":
    main()
