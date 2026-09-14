from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict


class RunLogEntry(TypedDict):
    run_id: str
    issue_number: int
    decision: str
    reason: str
    evidence_hash: str
    timestamp: str


def append_entry(log: list[RunLogEntry], entry: RunLogEntry) -> list[RunLogEntry]:
    """Doubles as the write audit trail (every write has a corresponding
    entry) and the idempotency source of truth (every run's evidence hash
    is recorded here, not just runs that produced a write) - a noop needs a
    comparison point too, or a steady-state issue would call the model and
    recompute evidence every single run forever.
    """
    return [*log, entry]


def find_latest_for_issue(log: list[RunLogEntry], issue_number: int) -> RunLogEntry | None:
    for entry in reversed(log):
        if entry["issue_number"] == issue_number:
            return entry
    return None


def load_run_log(path: Path) -> list[RunLogEntry]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return []


def save_run_log(path: Path, log: list[RunLogEntry]) -> None:
    path.write_text(json.dumps(log, indent=2))
