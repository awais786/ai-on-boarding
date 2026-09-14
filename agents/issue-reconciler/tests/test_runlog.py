from __future__ import annotations

from issue_reconciler.state.runlog import append_entry, find_latest_for_issue


def _entry(**overrides):
    base = {
        "run_id": "run-1",
        "issue_number": 1,
        "decision": "noop",
        "reason": "no evidence",
        "evidence_hash": "abc",
        "timestamp": "2026-09-14T00:00:00+00:00",
    }
    return {**base, **overrides}


def test_find_latest_for_issue_returns_none_when_the_issue_has_no_entries():
    assert find_latest_for_issue([], 1) is None


def test_find_latest_for_issue_returns_the_most_recent_entry_for_that_issue_only():
    log = append_entry([], _entry(issue_number=1, evidence_hash="first"))
    log = append_entry(log, _entry(issue_number=2, evidence_hash="other-issue"))
    log = append_entry(log, _entry(issue_number=1, evidence_hash="second"))

    latest = find_latest_for_issue(log, 1)

    assert latest["evidence_hash"] == "second"


def test_append_entry_does_not_mutate_the_original_log():
    original = []
    updated = append_entry(original, _entry())

    assert len(original) == 0
    assert len(updated) == 1
