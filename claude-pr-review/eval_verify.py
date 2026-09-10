"""Run verify.py against a saved fixture instead of a live PR, so verify.md
changes can be tested repeatably without a paid CI cycle or a real GitHub
PR. Still spends real API money per trial - nothing here runs itself.

A fixture is a directory with diff.txt (unified diff, any format target.py
would have produced), rules.json ({"path": "contents", ...}, target.py's
repo_rules() shape), and findings.json (judge.py's output shape, the
{"findings": [...]} Layer 2 would have produced). fixtures/debug-files/ was
captured from a real judge.py run against PR #6/#7 on habib049/ai-on-boarding
(the throwaway debug_secret.py/debug_logging.py/debug_password_check.py
smoke test) - reuse it, or add a new directory in the same shape for a
different scenario.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anthropic

import verify


def load_fixture(fixture_dir: Path) -> tuple[str, dict, dict]:
    diff = (fixture_dir / "diff.txt").read_text()
    rules = json.loads((fixture_dir / "rules.json").read_text())
    findings = json.loads((fixture_dir / "findings.json").read_text())
    return diff, rules, findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="Path to a fixture directory")
    parser.add_argument("--trials", type=int, default=1, help="Run this many times, for variance")
    args = parser.parse_args()

    diff, rules, findings = load_fixture(args.fixture)
    client = anthropic.Anthropic()

    for trial in range(1, args.trials + 1):
        try:
            result = verify.verify(client, diff, rules, findings)
        except Exception as exc:
            print(f"=== {args.fixture.name} trial {trial}/{args.trials}: CRASHED: {exc} ===",
                  file=sys.stderr)
            continue
        print(f"=== {args.fixture.name} trial {trial}/{args.trials}: "
              f"{len(result['findings'])}/{len(findings.get('findings', []))} findings kept ===")
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
