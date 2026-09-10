"""Layer 3: independently re-check Layer 2's findings before any of them can
block a merge - confirms each citation is real and each failure scenario
actually holds, dropping or downgrading anything that doesn't check out.

Verifies one finding per agent.run() call, not the whole batch in one call.
A live test (PR #7, run 34456550640) showed the batched version had no way
to stop one hard finding from consuming the entire tool-use budget and
starving the rest - splitting per-finding bounds that structurally: a stuck
or wrong verification on one finding can't affect any other, each gets its
own fresh MAX_ITERATIONS budget, and a failure on one finding (see verify()'s
except clause) drops just that finding rather than losing the whole run.
The diff+rules content is identical across every call for one PR, so
it's passed as agent.run()'s cached stable_content and only the one
finding being checked varies per call - see agent.py's cache_control
handling for why that keeps the repeated-call cost down.
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


def build_stable_content(diff: str, rules: dict) -> str:
    return json.dumps({"diff": diff, "rules": rules})


def verify(client, diff: str, rules: dict, findings: dict) -> dict:
    items = findings.get("findings", [])
    if not items:
        return {"findings": []}

    stable_content = build_stable_content(diff, rules)
    verified = []
    for finding in items:
        variable_content = json.dumps({"finding": finding})
        try:
            result = agent.run(client, MODEL, SYSTEM_PROMPT, stable_content, variable_content)
        except agent.AgentError as exc:
            print(
                f"[verify] could not verify finding, dropping it: {exc}\n"
                f"  {finding.get('file')}:{finding.get('line')} - {finding.get('summary', '')[:120]}",
                file=sys.stderr,
            )
            continue
        verified.extend(result.get("findings", []))
    return {"findings": verified}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="PR number, branch, or omit for the working tree")
    parser.add_argument("--findings", type=Path, required=True, help="Path to judge.py's output JSON")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    findings = json.loads(args.findings.read_text())
    client = anthropic.Anthropic()
    diff = target.get_diff(args.target)
    rules = target.repo_rules()
    result = verify(client, diff, rules, findings)

    output = json.dumps(result, indent=2)
    print(output)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
