from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

# issue_number (as str, since JSON object keys are always strings) -> ISO expires_at
LeaseState = dict[str, str]


def is_leased(state: LeaseState, issue_number: int, now: datetime) -> bool:
    expires_at = state.get(str(issue_number))
    return expires_at is not None and datetime.fromisoformat(expires_at) > now


def acquire_lease(state: LeaseState, issue_number: int, ttl_seconds: int, now: datetime) -> LeaseState | None:
    """Returns None if already leased and unexpired; otherwise the updated state."""
    if is_leased(state, issue_number, now):
        return None
    return {**state, str(issue_number): (now + timedelta(seconds=ttl_seconds)).isoformat()}


def release_lease(state: LeaseState, issue_number: int) -> LeaseState:
    next_state = dict(state)
    next_state.pop(str(issue_number), None)
    return next_state


def load_lease_state(path: Path) -> LeaseState:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def save_lease_state(path: Path, state: LeaseState) -> None:
    path.write_text(json.dumps(state, indent=2))
