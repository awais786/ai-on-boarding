from __future__ import annotations

from datetime import datetime, timezone

from issue_reconciler.fingerprint import build_fingerprint
from issue_reconciler.policy.rules import AGENT_ACTOR
from issue_reconciler.spokes.board_history import summarize_history

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


def test_no_comments_means_no_known_actor_and_no_transitions():
    result = summarize_history([], NOW)
    assert result == {"last_status_actor": None, "last_status_at": None, "transition_count": 0}


def test_a_plain_human_comment_is_treated_as_the_last_human_touch():
    comments = [{"author": "alice", "body": "please hold off on this one", "created_at": "2026-09-14T10:00:00+00:00"}]

    result = summarize_history(comments, NOW)

    assert result == {"last_status_actor": "alice", "last_status_at": "2026-09-14T10:00:00+00:00", "transition_count": 0}


def test_a_fingerprinted_comment_is_attributed_to_the_agent_not_the_pat_owner():
    fp = build_fingerprint({"run_id": "run-1", "decision": "set_in_progress", "evidence_hash": "abc123"})
    comments = [{"author": "a-human-owned-pat", "body": f"In progress - PR #5 open.\n{fp}", "created_at": "2026-09-14T09:00:00+00:00"}]

    result = summarize_history(comments, NOW)

    assert result["last_status_actor"] == AGENT_ACTOR
    assert result["last_status_at"] == "2026-09-14T09:00:00+00:00"
    assert result["transition_count"] == 1


def test_counts_only_transition_decisions_within_the_lookback_window():
    in_window = build_fingerprint({"run_id": "r1", "decision": "set_in_progress", "evidence_hash": "a"})
    flag_decision = build_fingerprint({"run_id": "r2", "decision": "flag", "evidence_hash": "b"})
    outside_window = build_fingerprint({"run_id": "r3", "decision": "set_done", "evidence_hash": "c"})

    comments = [
        {"author": "bot", "body": f"old\n{outside_window}", "created_at": "2026-09-01T00:00:00+00:00"},
        {"author": "bot", "body": f"flagged\n{flag_decision}", "created_at": "2026-09-13T00:00:00+00:00"},
        {"author": "bot", "body": f"recent\n{in_window}", "created_at": "2026-09-14T00:00:00+00:00"},
    ]

    result = summarize_history(comments, NOW)

    assert result["transition_count"] == 1


def test_a_human_comment_after_the_agent_last_wrote_overrides_the_actor():
    fp = build_fingerprint({"run_id": "r1", "decision": "set_in_progress", "evidence_hash": "a"})
    comments = [
        {"author": "bot", "body": f"automated\n{fp}", "created_at": "2026-09-13T00:00:00+00:00"},
        {"author": "bob", "body": "actually I am handling this", "created_at": "2026-09-14T08:00:00+00:00"},
    ]

    result = summarize_history(comments, NOW)

    assert result["last_status_actor"] == "bob"
    assert result["last_status_at"] == "2026-09-14T08:00:00+00:00"
