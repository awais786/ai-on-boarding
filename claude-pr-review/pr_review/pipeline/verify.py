"""Layer 3: independently re-check Layer 2's findings before any of them can
block a merge - confirms each citation is real and each failure scenario
actually holds. Verification and classification are different jobs: Layer 3
can only confirm/reject a citation and upgrade a severity, never assign or
lower one - see agent.VERIFICATION_SCHEMA and _apply_verification().

Two of the three citation forms (a ruff code, a quoted convention string, a
named test) are mechanically checkable - precheck() does that in code,
deterministically, for free (folded in from what used to be citations.py:
its only caller was this module). Only a citation precheck can't resolve
(NEEDS_MODEL) spends a real agent.run() call. On a typical PR that cuts
Layer 3's call volume by roughly a third.

The model is never told Layer 2's severity - a verifier told "this is
CRITICAL" tends to find reasons it's critical; asked to independently assess
and only optionally escalate, it doesn't inherit the bias. CRITICAL-severity
findings route to Sonnet rather than Haiku (MODEL_FOR_SEVERITY): getting a
CRITICAL verdict wrong is the expensive direction to be wrong in, and the
citation precheck's cut to call volume is what makes that affordable.

Verifies one finding per agent.run() call, not the whole batch in one call.
A live test (PR #7, run 34456550640) showed the batched version had no way
to stop one hard finding from consuming the entire tool-use budget and
starving the rest - splitting per-finding bounds that structurally: a stuck
or wrong verification on one finding can't affect any other, each gets its
own fresh MAX_ITERATIONS budget.

Fails closed: agent.call_with_retries() exhausting its attempts is not
evidence against the finding, so severity and citation are preserved as-is
(marked `unverified: true` for a human to see) rather than stripping the
citation and letting infrastructure flake unblock a merge.

The diff+rules content is identical across every call for one PR, so
it's passed as agent.run()'s cached stable_content and only the one
finding being checked varies per call - see agent.py's cache_control
handling for why that keeps the repeated-call cost down.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from enum import Enum
from pathlib import Path

import anthropic

from pr_review.core import agent, target, tools
from pr_review.lib import severity

MODEL_HAIKU = "claude-haiku-4-5"
MODEL_SONNET = "claude-sonnet-5"
# Haiku doesn't support the task_budget beta (agent.py's TASK_BUDGET_BETA),
# so only the Sonnet route gets one; Haiku relies on MAX_ITERATIONS alone,
# same as before this table existed - now explicit per route rather than
# uniform across all of Layer 3.
MODEL_FOR_SEVERITY = {"CRITICAL": MODEL_SONNET, "MAJOR": MODEL_HAIKU, "MINOR": MODEL_HAIKU}
SONNET_TASK_BUDGET = agent.MIN_TASK_BUDGET_TOKENS

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"  # claude-pr-review/prompts/, not beside this file
SYSTEM_PROMPT = (PROMPTS_DIR / "verify.md").read_text()

_TEST_DEF_RE = re.compile(r"^\s*def (test_[A-Za-z0-9_]+)", re.M)
_QUOTE_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')
_TEST_NAME_RE = re.compile(r"\btest_[A-Za-z0-9_]+\b")


# --- citation precheck (pure - no I/O, no model call) -----------------------
#
# `ctx` (below, _Context) exposes convention_text and test_index. Note what
# it deliberately does NOT carry: Layer 1's raw per-location ruff codes -
# see precheck()'s `ruff:` branch for why looking them up would weaken the
# citation contract rather than complete it.

class Precheck(Enum):
    CONFIRMED = "confirmed"      # skip the model, citation is valid
    REJECTED = "rejected"        # citation is false; strip it, keep the finding
    NEEDS_MODEL = "needs_model"


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def extract_quoted(text: str) -> str | None:
    match = _QUOTE_RE.search(text)
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def extract_test_name(text: str) -> str | None:
    match = _TEST_NAME_RE.search(text)
    return match.group(0) if match else None


def precheck(finding: dict, ctx) -> Precheck:
    if finding.get("source") == "lint":
        return Precheck.CONFIRMED

    cit = (finding.get("citation") or "").strip()
    if not cit:
        return Precheck.REJECTED

    if cit.startswith("ruff:"):
        # Reaching here means a MODEL finding claimed a ruff code, because a
        # genuine one arrives as source == "lint" and was confirmed above.
        # If ruff had actually flagged that code at that location,
        # judge._lint_as_findings() would have produced the finding and
        # judge.merge_lint_and_model() would have folded any nearby model
        # finding into it - carrying source == "lint" with it. So what's
        # left is a ruff code the linter did not produce here: misapplied
        # or invented either way, and not something to confirm on the
        # model's say-so. The finding itself survives with citation set to
        # null, so nothing is lost by rejecting.
        return Precheck.REJECTED

    quote = extract_quoted(cit)
    if quote:
        hay = normalize(ctx.convention_text)
        return Precheck.CONFIRMED if normalize(quote) in hay else Precheck.REJECTED

    test_name = extract_test_name(cit)
    if test_name:
        return Precheck.CONFIRMED if test_name in ctx.test_index else Precheck.REJECTED

    return Precheck.NEEDS_MODEL


class _Context:
    """precheck()'s ctx.

    `test_index` is a whole-repo scan - every .py file read to find test
    function names - so it is built lazily on first use rather than per
    verify() call. Most PRs never reach it: a finding is only checked
    against it when its citation names a test, and lint-sourced or
    quote-citing findings resolve without ever touching it. Eagerly
    scanning meant paying for a full tree walk on every run, including
    runs with nothing but lint findings.
    """

    def __init__(self, convention_text: str):
        self.convention_text = convention_text
        self._test_index: set[str] | None = None

    @property
    def test_index(self) -> set[str]:
        if self._test_index is None:
            self._test_index = _build_test_index()
        return self._test_index


def _build_test_index() -> set[str]:
    names: set[str] = set()
    for root, dirnames, filenames in os.walk(target.REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in tools.SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            try:
                content = (Path(root) / name).read_text(errors="replace")
            except OSError:
                continue
            names.update(_TEST_DEF_RE.findall(content))
    return names


# --- Layer 3 proper -----------------------------------------------------

def build_stable_content(diff: str, rules: dict) -> str:
    return json.dumps({"diff": agent.wrap_untrusted(diff), "rules": rules})


def _redact_for_model(finding: dict) -> str:
    # Don't prime the verifier with Layer 2's severity label - it should
    # reach its own judgment on how bad this is, then only ever escalate.
    redacted = {k: v for k, v in finding.items() if k not in ("severity", "l2_severity")}
    return json.dumps({"finding": redacted})


def _apply_verification(finding: dict, verdict: dict) -> list[dict]:
    if not verdict.get("verified", False):
        return []  # the claimed failure scenario doesn't actually hold

    out = dict(finding)
    if not verdict.get("citation_holds", False):
        out["citation"] = None
    escalate_to = verdict.get("escalate_to")
    if escalate_to:
        out["severity"] = severity.max_severity(out["severity"], escalate_to)
    out["verified"] = True
    return [out]


def _verify_one(client, stable_content: str, finding: dict) -> list[dict]:
    model = MODEL_FOR_SEVERITY.get(finding.get("l2_severity"), MODEL_HAIKU)
    task_budget = SONNET_TASK_BUDGET if model == MODEL_SONNET else None
    variable_content = _redact_for_model(finding)

    verdict, error = agent.call_with_retries(lambda: agent.run(
        client, model, SYSTEM_PROMPT, stable_content, variable_content,
        output_schema=agent.VERIFICATION_SCHEMA, task_budget=task_budget,
    ))
    if error is None:
        return _apply_verification(finding, verdict)

    # Every retry failed. Not evidence against the finding - keep it as-is
    # (severity and citation untouched, never downgraded) so infrastructure
    # flake can't unblock a merge; gate.py's blocking condition is unchanged,
    # so this only blocks if the original finding already would have.
    print(
        f"[verify] verification unavailable, keeping finding as-is: {error}\n"
        f"  {finding.get('file')}:{finding.get('line')} - {finding.get('summary', '')[:120]}",
        file=sys.stderr,
    )
    unverified = dict(finding)
    unverified["unverified"] = True
    unverified["unverified_reason"] = str(error)
    return [unverified]


def verify(client, diff: str, rules: dict, findings: dict) -> dict:
    items = findings.get("findings", [])
    if not items:
        return {"findings": []}

    ctx = _Context(convention_text="\n".join(rules.values()))
    stable_content = build_stable_content(diff, rules)
    verified = []
    for original in items:
        # l2_severity is Layer 2's own verdict, carried through every path
        # below unchanged - gate.py asserts final severity never ranks
        # below it (invariant 4: Layer 3 may escalate, never downgrade).
        finding = dict(original)
        finding["l2_severity"] = finding.get("severity")

        if finding.get("source") == "lint":
            # ruff already confirmed this - not a model claim to re-check.
            verified.append(finding)
            continue

        outcome = precheck(finding, ctx)
        if outcome is Precheck.CONFIRMED:
            verified.append(finding)
            continue
        if outcome is Precheck.REJECTED:
            # The citation doesn't check out, but that isn't grounds to drop
            # a real bug - strip the citation (so it can never block) and
            # keep the finding, severity untouched.
            rejected = dict(finding)
            rejected["citation"] = None
            verified.append(rejected)
            continue

        verified.extend(_verify_one(client, stable_content, finding))

    result = {"findings": verified}
    if "suppressed_count" in findings:
        result["suppressed_count"] = findings["suppressed_count"]
    return result


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
