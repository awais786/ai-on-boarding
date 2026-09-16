"""Two small hashes the rest of the system leans on:

- fingerprint: a marker stamped in every real comment so board_history can
  tell the agent's own writes apart from a human's, even though the PAT
  backing those writes belongs to a human account.
  Format: <!-- issue-reconciler: v1 run=<id> decision=<action> evidence=sha256:<hex> -->
- evidence hash: the idempotency key, hash(issue_number + evidence).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import TypedDict

from issue_reconciler.rules import human_override_active
from issue_reconciler.types import Evidence

_FINGERPRINT_RE = re.compile(r"<!--\s*issue-reconciler:\s*v1\s+run=(\S+)\s+decision=(\S+)\s+evidence=sha256:([0-9a-f]+)\s*-->")
_DRY_RUN_MARKER_RE = re.compile(r"<!--\s*issue-reconciler:\s*dry-run\s")


class Fingerprint(TypedDict):
    run_id: str
    decision: str
    evidence_hash: str


def build_fingerprint(fp: Fingerprint) -> str:
    return f"<!-- issue-reconciler: v1 run={fp['run_id']} decision={fp['decision']} evidence=sha256:{fp['evidence_hash']} -->"


def parse_fingerprint(comment_body: str) -> Fingerprint | None:
    match = _FINGERPRINT_RE.search(comment_body)
    if not match:
        return None
    run_id, decision, evidence_hash = match.groups()
    return {"run_id": run_id, "decision": decision, "evidence_hash": evidence_hash}


def is_agent_comment(comment_body: str) -> bool:
    """True for a real, fingerprinted transition comment *or* a dry-run
    preview - both are the bot's own writes, posted through the human-owned
    PAT. Only the former counts toward transition_count (a dry run didn't
    really transition anything), but both must be recognized as the bot's
    own voice here - otherwise summarize_history reads a dry-run comment's
    author (the PAT's human account) as a genuine human status change, and
    the next real run within 24h treats it as a human override.
    """
    return parse_fingerprint(comment_body) is not None or _DRY_RUN_MARKER_RE.search(comment_body) is not None


# Fields on each LinkedPR that churn from ordinary PR activity (a push, a
# review) without changing what the rule engine or the reasoning spokes'
# provisional read of the PR would conclude. Hashing them raw meant any push
# to a still-open PR produced a "new" evidence hash - a fresh "In progress"
# comment every run, and eventually a false flapping flag once three of
# those landed inside the 7-day lookback.
_VOLATILE_PR_FIELDS = ("updated_at", "review_decision")


def _stable_linked_pr(pr: dict) -> dict:
    return {k: v for k, v in pr.items() if k not in _VOLATILE_PR_FIELDS}


def hash_evidence(evidence: Evidence, now: datetime) -> str:
    """json.dumps(sort_keys=True) recurses into nested lists-of-dicts too,
    so this stays stable regardless of key insertion order.

    last_status_actor/last_status_at are replaced with the single derived
    boolean decide_action actually uses (human_override_active): hashing
    the raw fields would change on every one of the bot's own comments
    (last_status_actor becomes the bot, last_status_at becomes "now"), so
    "unchanged evidence" would never match again after the bot's first
    write - but collapsing them to nothing (an earlier version of this
    function) broke the opposite case: once a human's override window
    genuinely elapses, the hash needs to change too, or the issue is stuck
    unprocessed forever. This derived boolean flips exactly when the
    override's live/expired state flips, not on every unrelated write.

    transition_count is excluded too, and for the same self-perpetuating
    reason: incrementing it is itself a side effect of the bot's own last
    comment, so including it raw means any single hash-changing event
    triggers a comment, which bumps transition_count, which changes the
    hash again next run, which triggers another comment... a cascade that
    hits the flapping threshold on its own within 3 runs even though the
    underlying PR state stopped changing after the first one. decide_action
    still sees the real, current transition_count on every run where it
    actually runs (this only gates whether it runs at all), so genuine
    flapping - the external PR state itself changing repeatedly - is still
    caught correctly. current_status stays in the hash as-is: it's a
    genuinely external signal (a real board move) that should force
    reprocessing.
    """
    hashed = {
        **{k: v for k, v in evidence.items() if k not in ("last_status_actor", "last_status_at", "transition_count", "linked_prs")},
        "human_override_active": human_override_active(evidence, now),
        "linked_prs": [_stable_linked_pr(pr) for pr in evidence["linked_prs"]],
    }
    canonical = json.dumps(hashed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
