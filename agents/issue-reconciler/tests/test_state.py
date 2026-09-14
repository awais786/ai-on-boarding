from __future__ import annotations

from datetime import datetime, timedelta, timezone

from issue_reconciler.state import (
    acquire_lease,
    find_latest_for_issue,
    is_leased,
    release_lease,
)

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
TTL = 5 * 60


def test_acquire_lease_then_reject_a_second_acquire_until_expiry():
    leased = acquire_lease({}, 1, TTL, NOW)
    assert is_leased(leased, 1, NOW)
    assert acquire_lease(leased, 1, TTL, NOW) is None  # still held

    later = NOW + timedelta(seconds=TTL + 1)
    assert is_leased(leased, 1, later) is False
    assert acquire_lease(leased, 1, TTL, later) is not None  # expired, reacquirable


def test_release_lease_only_affects_the_given_issue():
    state = acquire_lease({}, 1, TTL, NOW)
    state = acquire_lease(state, 2, TTL, NOW)

    released = release_lease(state, 1)

    assert is_leased(released, 1, NOW) is False
    assert is_leased(released, 2, NOW)


def _entry(issue_number, evidence_hash):
    return {"run_id": "r", "issue_number": issue_number, "decision": "noop", "reason": "x", "evidence_hash": evidence_hash, "timestamp": "2026-09-14T00:00:00+00:00"}


def test_find_latest_for_issue_returns_none_or_the_most_recent_entry():
    assert find_latest_for_issue([], 1) is None

    log = [_entry(1, "first"), _entry(2, "other-issue"), _entry(1, "second")]
    assert find_latest_for_issue(log, 1)["evidence_hash"] == "second"
