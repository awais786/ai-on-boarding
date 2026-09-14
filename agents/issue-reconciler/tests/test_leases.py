from __future__ import annotations

from datetime import datetime, timedelta, timezone

from issue_reconciler.state.leases import acquire_lease, is_leased, release_lease

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
TTL = 5 * 60


def test_acquiring_a_lease_on_an_unleased_issue_succeeds():
    result = acquire_lease({}, 1, TTL, NOW)
    assert result is not None
    assert is_leased(result, 1, NOW)


def test_acquiring_a_lease_on_an_already_leased_unexpired_issue_fails():
    leased = acquire_lease({}, 1, TTL, NOW)
    result = acquire_lease(leased, 1, TTL, NOW)
    assert result is None


def test_a_lease_can_be_reacquired_once_it_has_expired():
    leased = acquire_lease({}, 1, TTL, NOW)
    later = NOW + timedelta(seconds=TTL + 1)
    assert is_leased(leased, 1, later) is False
    assert acquire_lease(leased, 1, TTL, later) is not None


def test_releasing_a_lease_removes_it_and_does_not_affect_other_issues():
    state = acquire_lease({}, 1, TTL, NOW)
    state = acquire_lease(state, 2, TTL, NOW)

    released = release_lease(state, 1)

    assert is_leased(released, 1, NOW) is False
    assert is_leased(released, 2, NOW)
