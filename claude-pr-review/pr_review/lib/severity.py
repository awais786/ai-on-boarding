"""Severity taxonomy and ruff-code mapping. Pure - no I/O, no model calls,
no imports from judge.py or verify.py.
"""
from __future__ import annotations

# Every prefix must be one ruff.toml actually selects - test_lint_layer.py
# asserts the two stay in sync. `W`/`N` are absent since they'd map to
# MINOR anyway, same as an unrecognized code.
RUFF_SEVERITY = {
    "S": "CRITICAL",      # bandit / security - hardcoded secrets, eval, injection
    "F82": "MAJOR",       # undefined name
    "F81": "MAJOR",       # redefinition
    "B": "MAJOR",         # bugbear
    "F": "MINOR",         # remaining pyflakes (F401 etc.)
    "E": "MINOR",
    "I": "MINOR",
}

RANK = {"MINOR": 1, "MAJOR": 2, "CRITICAL": 3}

BLOCKING_SEVERITIES = {"CRITICAL", "MAJOR"}


def is_blocking(finding: dict) -> bool:
    """Whether this finding fails the merge gate. Lives here so gate.py
    (which renders the verdict) and state.py (which refuses to let a
    checkbox waive one) can never drift apart on what "blocking" means.

    Two ways to qualify, because a citation and a verification are evidence
    of different things:

    - CITED, at CRITICAL or MAJOR. The citation shows some rule this repo
      actually agreed on is being broken.
    - UNCITED, but CRITICAL and independently confirmed by Layer 3. Some
      defects are true without this repo having written them down; for
      those the verification is the evidence and a citation would only be
      paperwork. `verified` is set solely by verify._apply_verification(),
      so a lint passthrough or a finding Layer 3 never saw can't qualify.
    """
    severity_value = finding.get("severity")
    if severity_value not in BLOCKING_SEVERITIES:
        return False
    if finding.get("citation"):
        return True
    return severity_value == "CRITICAL" and finding.get("verified") is True


def severity_for_ruff(code: str) -> str:
    """Map a ruff rule code to a severity. Longest-prefix match: F821 must
    hit F82 before the generic F bucket.
    """
    for prefix in sorted(RUFF_SEVERITY, key=len, reverse=True):
        if code.startswith(prefix):
            return RUFF_SEVERITY[prefix]
    return "MINOR"


def max_severity(a: str, b: str) -> str:
    return a if RANK[a] >= RANK[b] else b
