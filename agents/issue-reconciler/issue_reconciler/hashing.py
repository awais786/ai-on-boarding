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
from typing import TypedDict

from issue_reconciler.types import Evidence

_FINGERPRINT_RE = re.compile(r"<!--\s*issue-reconciler:\s*v1\s+run=(\S+)\s+decision=(\S+)\s+evidence=sha256:([0-9a-f]+)\s*-->")


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


_TRANSITION_HISTORY_FIELDS = ("last_status_actor", "last_status_at", "transition_count")


def hash_evidence(evidence: Evidence) -> str:
    """json.dumps(sort_keys=True) recurses into nested lists-of-dicts too,
    so this stays stable regardless of key insertion order.

    Excludes last_status_actor/last_status_at/transition_count: those are
    derived from the bot's own prior comments (board_history), so they
    change on every run that writes a comment - hashing them would make
    "unchanged evidence" never match after the bot's first write, and a
    steady, still-open PR would get a fresh in-progress comment every run
    until it looked like flapping. current_status stays in the hash: it's
    genuinely external state (and still forces a retry if a mutation
    partially failed, e.g. status set but close failed).
    """
    hashed = {k: v for k, v in evidence.items() if k not in _TRANSITION_HISTORY_FIELDS}
    canonical = json.dumps(hashed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
