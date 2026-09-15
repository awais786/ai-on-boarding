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


def test_summary_links_issue_and_relevant_pr():
    merged_pr = {"number": 28, "merged": True, "state": "MERGED"}
    processed = [_issue(issue_number=9, evidence={"linked_prs": [merged_pr]})]
    summary = build_summary(processed)
    assert "<https://github.com/awais786/ai-on-boarding/issues/9|#9>" in summary
    assert "<https://github.com/awais786/ai-on-boarding/pull/28|#28>" in summary
    assert summary.startswith("Issue reconciler ran on 1 issue(s), 1 changed, 0 untouched (no linked PR):\nDone — ")


def test_summary_counts_untouched_issues_with_no_linked_pr():
    processed = [
        _issue(issue_number=1, evidence={"linked_prs": [{"number": 28, "merged": True, "state": "MERGED"}]}),
        _issue(issue_number=2, decision={"action": "noop", "reason": "no evidence"}, evidence={"linked_prs": []}),
        _issue(issue_number=3, decision={"action": "noop", "reason": "no evidence"}, evidence={"linked_prs": []}),
        _issue(issue_number=4, skipped="leased", decision={"action": "noop", "reason": "already leased"}, evidence=None),
    ]
    summary = build_summary(processed)
    assert "4 issue(s), 1 changed, 2 untouched (no linked PR)" in summary


def test_flag_summary_links_every_linked_pr():
    prs = [{"number": 16, "merged": True, "state": "MERGED"}, {"number": 17, "merged": False, "state": "OPEN"}]
    processed = [_issue(issue_number=9, decision={"action": "flag", "reason": "mixed PR states"}, evidence={"linked_prs": prs})]
    summary = build_summary(processed)
    assert "#16" in summary
    assert "#17" in summary
