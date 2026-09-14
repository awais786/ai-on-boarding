from __future__ import annotations

import hashlib
import json

from issue_reconciler.types import Evidence


def _stable_dumps(value: object) -> str:
    """json.dumps(sort_keys=True) only sorts dict keys, which is all we
    need here - Evidence has no nested dicts, only lists of dicts, and
    sort_keys already recurses into those. Kept separate from json.dumps
    call sites so the "why" (a stable hash, not just readable JSON) is
    documented once.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def hash_evidence(evidence: Evidence) -> str:
    """The idempotency key: hash(issue_number + evidence), per the plan."""
    return hashlib.sha256(_stable_dumps(evidence).encode("utf-8")).hexdigest()
