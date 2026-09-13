"""Layer 3: independently re-check Layer 2's findings before any can block
a merge - confirms each citation is real and each failure scenario holds.
Can only confirm/reject a citation and upgrade a severity, never assign or
lower one - see agent.VERIFICATION_SCHEMA and _apply_verification().

Two of three citation forms (a ruff code, a quoted convention string, a
named test) are mechanically checkable - precheck() does that in code,
for free, cutting model call volume by roughly a third. Only what precheck
can't resolve (NEEDS_MODEL) spends a real agent.run() call.

The model is never told Layer 2's severity, so it doesn't inherit the bias
of confirming a label it's shown. Every verification runs on the strong
model (MODEL) - see the comment there for why a weak verifier is worse than
none.

Verifies one finding per agent.run() call, not the whole batch at once -
a live test showed a batched call let one hard finding consume the whole
tool-use budget and starve the rest.

Fails closed: exhausted retries are not evidence against the finding, so
severity/citation are preserved as-is (marked `unverified: true`) rather
than stripping the citation and letting infra flake unblock a merge.

The diff+rules content is identical across calls for one PR, so it's
passed as agent.run()'s cached stable_content; only the finding varies.
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

# Every verification runs on the strong model, at every severity - this is
# the gate, and a weak verifier is worse than none: it drops real findings
# with the same confidence it drops invented ones. A live run with Haiku
# here rejected 4 of 5 model findings, including a genuine cross-file
# password-policy regression that Layer 2 had correctly found.
#
# Affordable because most findings never reach a model call at all: lint
# findings pass straight through, and precheck() settles the rest of the
# citations in code.
MODEL = "claude-sonnet-5"
TASK_BUDGET = agent.MIN_TASK_BUDGET_TOKENS

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "verify.md").read_text()

_TEST_DEF_RE = re.compile(r"^\s*def (test_[A-Za-z0-9_]+)", re.M)
_QUOTE_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')
_TEST_NAME_RE = re.compile(r"\btest_[A-Za-z0-9_]+\b")


# --- citation precheck (pure - no I/O, no model call) -----------------------
#
# `ctx` (below, _Context) exposes convention_text and test_index - not
# Layer 1's raw ruff codes; see precheck()'s `ruff:` branch for why.

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
        # Checked on its own merits rather than discarded. Some defects are
        # objectively true without this repo having written them down - MD5
        # for signing is broken whether or not CLAUDE.md says so - and for
        # those a citation is paperwork, not evidence. Layer 3's `verified`
        # answer IS the evidence, which is why the schema asks it
        # independently of `citation_holds`.
        #
        # MAJOR comes here too, so `escalate_to` can actually fire. Layer 2
        # under-rates security findings: a live run called two disagreeing
        # password policies on the same User model a MAJOR, which - being
        # uncited - was dropped here without ever reaching the one mechanism
        # designed to promote it. It still only BLOCKS if Layer 3 escalates
        # it to CRITICAL, so the bar is unchanged; what changes is that an
        # under-rated finding now gets the chance to be re-rated.
        if finding.get("l2_severity") in severity.BLOCKING_SEVERITIES:
            return Precheck.NEEDS_MODEL
        return Precheck.REJECTED

    if cit.startswith("ruff:"):
        # Reaching here means a MODEL finding claimed a ruff code - a
        # genuine one arrives as source == "lint" and was confirmed above.
        # So this is misapplied or invented either way; reject the
        # citation (the finding itself survives with citation set to null).
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
    """precheck()'s ctx. `test_index` is a whole-repo scan, built lazily on
    first use since most PRs never need it (only findings citing a test do).
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
        # Log the reasoning: a drop is the one outcome that leaves no trace
        # in the verdict, so without this a real finding lost here is
        # indistinguishable from one that was never raised.
        print(
            f"[verify] DROPPED {finding.get('file')}:{finding.get('line')} - "
            f"{(finding.get('summary') or '')[:90]}\n"
            f"         reason: {(verdict.get('reasoning') or '(none given)')[:300]}",
            file=sys.stderr,
        )
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
    variable_content = _redact_for_model(finding)

    verdict, error = agent.call_with_retries(lambda: agent.run(
        client, MODEL, SYSTEM_PROMPT, stable_content, variable_content,
        output_schema=agent.VERIFICATION_SCHEMA, task_budget=TASK_BUDGET,
    ))
    if error is None:
        return _apply_verification(finding, verdict)

    # Every retry failed. Not evidence against the finding - keep it as-is
    # so infrastructure flake can't unblock a merge.
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
    rejected_count = 0
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
            # a real bug - strip the citation and keep the finding.
            finding = dict(finding)
            finding["citation"] = None
            if finding.get("l2_severity") not in severity.BLOCKING_SEVERITIES:
                verified.append(finding)
                continue
            # A CRITICAL or MAJOR left uncited still gets checked on its own
            # merits, exactly like one that arrived with no citation at all.
            # Skipping it here was the same dead end in a different disguise:
            # a live run had Layer 2 "cite" a prompt-injection attempt using
            # the injected text itself, precheck correctly rejected that, and
            # the CRITICAL then sailed through unverified and unable to
            # block. Where a citation came from says nothing about whether
            # the underlying defect is real.

        outcome_findings = _verify_one(client, stable_content, finding)
        if not outcome_findings:
            # The model said the failure scenario doesn't hold, so the
            # finding is dropped. Counted rather than vanishing silently -
            # otherwise "Layer 3 rejected everything" and "Layer 2 found
            # nothing" look identical in the verdict.
            rejected_count += 1
        verified.extend(outcome_findings)

    result = {"findings": verified}
    if rejected_count:
        result["rejected_count"] = rejected_count
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
