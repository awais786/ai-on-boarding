"""Layer 2: judge a PR diff for architectural fit, convention compliance,
correctness, and blast radius. Runs Layer 1 (lint.py) first, merges any
model finding landing near a lint finding's (file, line) into it rather
than dropping it, and folds lint's findings into the output so they reach
Layer 4. Caps total findings so uncapped output doesn't multiply into
Layer 3 cost and comment spam.

`carried` is the summary of open findings a prior run already raised on
unchanged files - passed into the prompt only as "already raised, do not
repeat" context, never used to restrict the diff L2 sees (its blast-radius
analysis needs the whole change).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anthropic

from pr_review.core import agent, target
from pr_review.lib import severity
from pr_review.pipeline import lint

# Recall at Layer 2 is the ceiling on the whole pipeline: a finding raised
# here can still be rejected downstream, but one never raised can't be
# recovered by any later layer. Measured on the same PR, the cheap model
# found fewer real defects AND cited far fewer of them (1 of 5, against 4
# of 5) - and an uncited finding is one Layer 3 never even sees.
MODEL = "claude-sonnet-5"
# A ceiling on the whole judge run. The turn budget in judge.md is what
# should actually stop it; this is the backstop if the prompt doesn't hold.
TASK_BUDGET_TOKENS = 40_000
MAX_FINDINGS = 15
MERGE_WINDOW = 3
NOTE_PREFIX = "Layer 2 also notes:"
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "judge.md").read_text()


def build_user_content(diff: str, rules: dict, lint_result: dict, carried: list[dict] | None = None) -> str:
    payload = {"diff": agent.wrap_untrusted(diff), "rules": rules, "layer_1_lint_results": lint_result}
    if carried:
        payload["already_raised_on_this_pr"] = [
            {"file": f.get("file"), "line": f.get("line"), "summary": f.get("summary")}
            for f in carried
        ]
    return json.dumps(payload)


def _lint_as_findings(lint_result: dict) -> list[dict]:
    # ruff already confirmed these, so they carry their own citation and
    # skip Layer 3's re-verification. Severity comes from the rule family,
    # not a blanket MAJOR - an unused import isn't a broken auth path.
    return [
        {
            "file": f["file"],
            "line": f["line"],
            "severity": severity.severity_for_ruff(f["code"]),
            "summary": f["message"],
            "citation": f"ruff:{f['code']}",
            "source": "lint",
        }
        for f in lint_result.get("findings", [])
    ]


def merge_lint_and_model(lint_findings: list[dict], model_findings: list[dict], window: int = MERGE_WINDOW) -> list[dict]:
    out = [dict(f) for f in lint_findings]
    for mf in model_findings:
        hit = next(
            (
                lf for lf in out
                if lf["file"] == mf.get("file")
                and lf.get("line") is not None and mf.get("line") is not None
                and abs(lf["line"] - mf["line"]) <= window
            ),
            None,
        )
        if hit:
            # The lint message stays the headline since the citation attests
            # to it; replacing it with the model's prose could describe a
            # different problem than what the citation actually covers.
            model_summary = (mf.get("summary") or "").strip()
            if model_summary and model_summary not in hit["summary"]:
                # Avoid repeating the prefix if more than one model finding
                # lands near the same lint finding.
                connector = " — also: " if NOTE_PREFIX in hit["summary"] else f" — {NOTE_PREFIX} "
                hit["summary"] = f"{hit['summary']}{connector}{model_summary}"
            hit["severity"] = severity.max_severity(hit["severity"], mf.get("severity", "MINOR"))
        else:
            out.append(mf)
    return out


def _cap_findings(findings: list[dict], limit: int = MAX_FINDINGS) -> tuple[list[dict], int]:
    ranked = sorted(
        findings,
        key=lambda f: (severity.RANK.get(f.get("severity"), 0), bool(f.get("citation"))),
        reverse=True,
    )
    return ranked[:limit], max(0, len(findings) - limit)


def _run_layer_2(client, user_content: str) -> tuple[dict, str | None]:
    """The model half of Layer 2. Returns (result, error), never raises -
    a transient 500 here must not take down the whole run with no verdict.
    """
    result, error = agent.call_with_retries(lambda: agent.run(
        client, MODEL, SYSTEM_PROMPT, user_content, task_budget=TASK_BUDGET_TOKENS
    ))
    if error is None:
        return result, None
    print(f"[judge] Layer 2 unavailable: {error}", file=sys.stderr)
    return {"findings": []}, str(error)


def judge(client, target_arg: str | None, diff: str, rules: dict, carried: list[dict] | None = None) -> dict:
    """`diff` and `rules` are passed in, not fetched here, so Layer 2 and
    Layer 3 always review the identical bytes - fetching separately let a
    push landing mid-run give each layer a different diff.
    """
    lint_result = lint.scope_to_changed_lines(
        lint.run(target.changed_python_files(target_arg)),
        target.changed_lines(diff),
    )
    user_content = build_user_content(diff, rules, lint_result, carried)

    result, layer2_error = _run_layer_2(client, user_content)

    # Layer 1's findings still ship even when Layer 2 didn't - a lint-only
    # review beats none. The error carries through to force a blocking
    # verdict rather than a false "ready to merge".
    merged = merge_lint_and_model(_lint_as_findings(lint_result), result.get("findings", []))
    kept, suppressed_count = _cap_findings(merged)

    result["findings"] = kept
    result["suppressed_count"] = suppressed_count
    if layer2_error:
        result["layer2_error"] = layer2_error
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", help="PR number, branch, or omit for the working tree")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    client = anthropic.Anthropic()
    result = judge(client, args.target, target.get_diff(args.target), target.repo_rules())

    output = json.dumps(result, indent=2)
    print(output)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
