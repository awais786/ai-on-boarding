"""Shared by board_history (parses fingerprints left by earlier runs) and
the comment writer (stamps a new one on every comment). Keeping both in one
place means the format can never drift between reader and writer.
Format: <!-- issue-reconciler: v1 run=<id> decision=<action> evidence=sha256:<hex> -->
"""
from __future__ import annotations

import re
from typing import TypedDict

_FINGERPRINT_RE = re.compile(
    r"<!--\s*issue-reconciler:\s*v1\s+run=(\S+)\s+decision=(\S+)\s+evidence=sha256:([0-9a-f]+)\s*-->"
)


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
