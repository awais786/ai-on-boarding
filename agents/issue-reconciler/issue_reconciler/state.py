"""Leases (dispatch de-dup) and the run log (audit trail + idempotency
source of truth), each a plain dict/list persisted as JSON. Both are pure
functions over that data plus a thin load/save pair - no classes needed for
either.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict

LeaseState = dict[str, str]  # issue_number (as str) -> ISO expires_at


def is_leased(state: LeaseState, issue_number: int, now: datetime) -> bool:
    expires_at = state.get(str(issue_number))
    return expires_at is not None and datetime.fromisoformat(expires_at) > now


def acquire_lease(state: LeaseState, issue_number: int, ttl_seconds: int, now: datetime) -> LeaseState | None:
    """None if already leased and unexpired; otherwise the updated state."""
    if is_leased(state, issue_number, now):
        return None
    return {**state, str(issue_number): (now + timedelta(seconds=ttl_seconds)).isoformat()}


def release_lease(state: LeaseState, issue_number: int) -> LeaseState:
    return {k: v for k, v in state.items() if k != str(issue_number)}


class RunLogEntry(TypedDict):
    run_id: str
    issue_number: int
    decision: str
    reason: str
    evidence_hash: str
    timestamp: str


def find_latest_for_issue(log: list[RunLogEntry], issue_number: int) -> RunLogEntry | None:
    return next((e for e in reversed(log) if e["issue_number"] == issue_number), None)


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def load_lease_state(path: Path) -> LeaseState:
    return _load_json(path, {})


def load_run_log(path: Path) -> list[RunLogEntry]:
    return _load_json(path, [])


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2))
