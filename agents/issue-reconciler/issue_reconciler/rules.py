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


def decide_action(evidence: Evidence, *, now: datetime | None = None) -> Decision:
    now = now or datetime.now(timezone.utc)

    # 1. Ignore label always wins.
    if evidence["has_ignore_label"]:
        return {"action": "noop", "reason": "ignore label"}

    # 2. A recent human status change is never overridden.
    last_status_actor = evidence["last_status_actor"]
    last_status_at = evidence["last_status_at"]
    if _is_human_actor(last_status_actor) and last_status_at is not None:
        age = (now - datetime.fromisoformat(last_status_at)).total_seconds()
        if 0 <= age < HUMAN_OVERRIDE_WINDOW_SECONDS:
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
