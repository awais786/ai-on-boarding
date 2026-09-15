from __future__ import annotations

from issue_reconciler.slack import build_summary


def _issue(**overrides):
    return {"issue_number": 1, "decision": {"action": "set_done", "reason": "PR merged, none open"}, "skipped": None, **overrides}


def test_summary_lists_only_real_changes():
    processed = [
        _issue(issue_number=1),
        _issue(issue_number=2, decision={"action": "noop", "reason": "no evidence"}),
        _issue(issue_number=3, skipped="unchanged-evidence"),
    ]
    summary = build_summary(processed)
    assert "#1" in summary
    assert "#2" not in summary
    assert "#3" not in summary


def test_summary_is_none_when_nothing_changed():
    processed = [_issue(issue_number=1, decision={"action": "noop", "reason": "no evidence"})]
    assert build_summary(processed) is None
