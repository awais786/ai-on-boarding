"""Layer 2: judge a PR diff against architectural fit, this repo's own
conventions, functional correctness/completeness, and blast radius
(duplicated logic elsewhere in the codebase).

Runs Layer 1 (lint.py) itself first. Findings that land on the same
(file, line) as a Layer 1 finding are dropped programmatically after the
model responds - not left to a prompt instruction the model might not
follow. (An earlier prompt-only version of this rule was tested and did not
hold reliably; filtering in code cannot fail to hold.)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import agent
import anthropic
import lint
import schemas
import target

MODEL = "claude-sonnet-5"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "judge.md").read_text()


def build_user_content(target_arg: str | None, lint_result: dict) -> str:
    diff = target.get_diff(target_arg)
    rules = target.repo_rules()
    return json.dumps({"diff": diff, "rules": rules, "layer_1_lint_results": lint_result})


def _closed_locations(lint_result: dict) -> set[tuple[str, int | None]]:
    return {(f["file"], f["line"]) for f in lint_result.get("findings", [])}


def judge(client, target_arg: str | None) -> dict:
    lint_result = lint.run(target.changed_python_files(target_arg))
    user_content = build_user_content(target_arg, lint_result)

    result = agent.run(client, MODEL, SYSTEM_PROMPT, user_content, schemas.FINDINGS_SCHEMA)

    closed = _closed_locations(lint_result)
    result["findings"] = [
        f for f in result.get("findings", []) if (f.get("file"), f.get("line")) not in closed
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="PR number, branch, or omit for the working tree")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    client = anthropic.Anthropic()
    result = judge(client, args.target)

    output = json.dumps(result, indent=2)
    print(output)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
