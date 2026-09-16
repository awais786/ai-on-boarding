"""Pure policy engine: evidence in, decision out. No I/O, no model call.
Rules are evaluated in order; the first match wins.

Rules 5 and 6 were swapped from an earlier draft of the plan: PR state is
mutually exclusive per PR (OPEN, CLOSED, or MERGED), so "merged AND open
both present" only happens across *different* linked PRs. With "any PR
open" checked first, that case always matched before the mixed-state rule
could ever fire, making it dead code. Checking the mixed case first makes
both rules reachable and routes the ambiguous case to a human instead of
silently resolving it as in-progress. See .claude/issue-reconciler-plan.md.
"""
from __future__ import annotations

from datetime import datetime, timezone

from issue_reconciler.types import Decision, Evidence

# Fingerprint prefix from HTML comments (see hashing.py). Any actor string
# equal to this is the agent's own write, not a human's.
AGENT_ACTOR = "issue-reconciler"

HUMAN_OVERRIDE_WINDOW_SECONDS = 24 * 60 * 60
FLAPPING_TRANSITION_COUNT = 3


def _is_human_actor(actor: str | None) -> bool:
    return actor is not None and actor != AGENT_ACTOR


def human_override_active(evidence: Evidence, now: datetime) -> bool:
    """Shared with hashing.py: the evidence hash needs this exact boolean,
    not the raw last_status_actor/last_status_at, so a run-log entry
    correctly falls stale once the override window elapses (see hashing.py).
    """
    actor = evidence["last_status_actor"]
    at = evidence["last_status_at"]
    if not _is_human_actor(actor) or at is None:
        return False
    age = (now - datetime.fromisoformat(at)).total_seconds()
    return 0 <= age < HUMAN_OVERRIDE_WINDOW_SECONDS


def decide_action(evidence: Evidence, *, now: datetime | None = None) -> Decision:
    now = now or datetime.now(timezone.utc)

    # 1. Ignore label always wins.
    if evidence["has_ignore_label"]:
        return {"action": "noop", "reason": "ignore label"}

    # 2. A recent human status change is never overridden.
    if human_override_active(evidence, now):
        return {"action": "noop", "reason": "human override"}

    # 3. Repeated agent flips indicate flapping; hand off to a human.
    if evidence["transition_count"] >= FLAPPING_TRANSITION_COUNT:
        return {"action": "flag", "reason": "flapping"}

    merged = [pr for pr in evidence["linked_prs"] if pr["merged"]]
    open_prs = [pr for pr in evidence["linked_prs"] if pr["state"] == "OPEN"]

    # 4. A merged PR with nothing still open closes the issue out.
    if merged and not open_prs:
        return {"action": "set_done", "reason": "PR merged, none open"}

    # 5. A merged PR alongside a still-open PR is ambiguous - a human decides.
    if merged and open_prs:
        return {"action": "flag", "reason": "mixed PR states"}

    # 6. An open PR (including draft) means work is in flight.
    if open_prs:
        return {"action": "set_in_progress", "reason": "PR open"}

    # 7. An OpenSpec proposal is also work in flight, absent a PR yet.
    if evidence["open_spec_proposals"]:
        return {"action": "set_in_progress", "reason": "OpenSpec proposal in flight"}

    # 8. No evidence of any work in flight.
    return {"action": "noop", "reason": "no evidence"}


def apply_verdicts(decision: Decision, verdicts: dict) -> Decision:
    """Post-processes decide_action()'s output against the four AI reasoning
    spokes. A verdict can only ever demote set_done/set_in_progress to flag
    - never confirm or upgrade a decision - so a spoke returning None ("no
    opinion", e.g. it wasn't run or its response was unusable) always means
    "no change here", never "assume the worst".
    """
    reference = verdicts.get("reference")
    if reference is not None and not reference["matches"]:
        return {"action": "flag", "reason": "PR reference does not appear to match this issue"}

    if decision["action"] == "set_done":
        stale = verdicts.get("stale")
        if stale is not None and stale["superseded"]:
            return {"action": "flag", "reason": "linked PR appears superseded by later work"}

        completion = verdicts.get("completion")
        if completion is not None and not completion["fully_resolved"]:
            return {"action": "flag", "reason": "PR merged but issue not fully resolved per completion check"}

    elif decision["action"] == "set_in_progress":
        activity = verdicts.get("activity")
        if activity is not None and activity["status"] == "abandoned":
            return {"action": "flag", "reason": "linked PR appears abandoned"}

    return decision
