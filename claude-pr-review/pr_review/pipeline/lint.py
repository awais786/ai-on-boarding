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

from pr_review.core.target import REPO_ROOT, changed_python_files

PR_REVIEW_DIR = Path(__file__).resolve().parents[2]  # claude-pr-review/ - where .venv, ruff.toml, build/ live


class LintError(RuntimeError):
    """ruff itself failed (bad config, crash, missing binary) - distinct from
    finding lint violations, which is ruff exiting 1 and working correctly.
    """


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

    # ruff exit 1 = violations found (handled below). Anything else means
    # ruff didn't run at all - must not be reported as "zero findings", or
    # judge.py would believe Layer 1 covered files it never actually linted.
    if result.returncode != 1:
        raise LintError(
            f"ruff exited {result.returncode} (expected 0 or 1) - no lint "
            f"coverage for these files:\n{result.stderr}"
        )

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


def scope_to_changed_lines(result: dict, changed: dict[str, set[int]]) -> dict:
    """Drop lint findings on lines the diff never touched.

    ruff lints each changed file WHOLE, which meant touching one line of a
    file made the PR responsible for every pre-existing violation in it - a
    live run blocked a PR on a B904 forty lines above anything it changed.
    Inheriting a file's lint debt because you edited its last function is
    not a defect the PR introduced.

    The trade: a change that makes existing code newly wrong (altering a
    function so code below it now misbehaves) is no longer caught here.
    That is Layer 2's job - it reads the whole file and the blast radius,
    which is exactly the kind of judgement a linter can't make anyway.

    Fails SAFE, unlike target.filter_diff(): a file absent from `changed`
    means the diff told us nothing about it, not that nothing in it
    changed, so its findings are KEPT. Dropping them would silently
    disable Layer 1 whenever diff parsing failed - and a review that
    reports nothing is indistinguishable from a clean one.
    """
    kept, dropped = [], 0
    for finding in result.get("findings", []):
        file_lines = changed.get(finding["file"])
        if file_lines is None or finding["line"] in file_lines:
            kept.append(finding)
        else:
            dropped += 1
    if dropped:
        print(
            f"[lint] {dropped} pre-existing finding(s) on untouched lines not reported",
            file=sys.stderr,
        )
    return {**result, "findings": kept, "status": "fail" if kept else "pass"}


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
