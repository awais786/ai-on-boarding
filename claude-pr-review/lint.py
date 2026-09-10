"""Layer 1: run ruff over the files the target changed (target.py). No LLM -
its findings are ground truth judge.py filters its own output against.
Lints each changed file whole, not just the touched lines.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from target import REPO_ROOT, changed_python_files

PR_REVIEW_DIR = Path(__file__).resolve().parent


def _ruff() -> str:
    # Prefer this dir's own .venv, then a console script beside the running
    # interpreter, then bare PATH lookup.
    candidates = [
        PR_REVIEW_DIR / ".venv" / "bin" / "ruff",
        Path(sys.executable).parent / "ruff",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "ruff"


def run(files: list[str]) -> dict:
    if not files:
        return {"status": "pass", "findings": []}

    result = subprocess.run(
        [
            _ruff(), "check",
            "--config", str(PR_REVIEW_DIR / "ruff.toml"),
            "--output-format", "json",
            *files,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return {"status": "pass", "findings": []}

    violations = json.loads(result.stdout or "[]")
    findings = [
        {
            "file": str(Path(v["filename"]).resolve().relative_to(REPO_ROOT)),
            "line": v["location"]["row"],
            "code": v["code"],
            "message": v["message"],
        }
        for v in violations
    ]
    return {"status": "fail", "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="PR number, branch, or omit for the working tree")
    parser.add_argument("--out", type=Path, default=PR_REVIEW_DIR / "build" / "lint_results.json")
    args = parser.parse_args()

    files = changed_python_files(args.target)
    result = run(files)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
