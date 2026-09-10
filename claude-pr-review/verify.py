"""Layer 3: independently re-check Layer 2's findings before any of them can
block a merge - confirms each citation is real and each failure scenario
actually holds, dropping or downgrading anything that doesn't check out.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import agent
import anthropic
import target

MODEL = "claude-haiku-4-5-20251001"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "verify.md").read_text()


def build_user_content(target_arg: str | None, findings: dict) -> str:
    diff = target.get_diff(target_arg)
    rules = target.repo_rules()
    return json.dumps({"diff": diff, "rules": rules, "findings": findings["findings"]})


def verify(client, target_arg: str | None, findings: dict) -> dict:
    if not findings.get("findings"):
        return {"findings": []}
    user_content = build_user_content(target_arg, findings)
    return agent.run(client, MODEL, SYSTEM_PROMPT, user_content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="PR number, branch, or omit for the working tree")
    parser.add_argument("--findings", type=Path, required=True, help="Path to judge.py's output JSON")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    findings = json.loads(args.findings.read_text())
    client = anthropic.Anthropic()
    result = verify(client, args.target, findings)

    output = json.dumps(result, indent=2)
    print(output)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
