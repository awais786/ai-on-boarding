from __future__ import annotations

from datetime import datetime, timezone

from issue_reconciler.fingerprint import parse_fingerprint
from issue_reconciler.writers.comment import (
    CommentContext,
    build_comment_body,
    should_comment,
)

CTX = CommentContext(run_id="run-abc", evidence_hash="deadbeef", logs_url="https://x/logs", now=datetime(2026, 9, 14, 17, 32, tzinfo=timezone.utc), dry_run=False)
MERGED = {"number": 88, "title": "x", "state": "MERGED", "merged": True, "merged_at": "2026-09-14T00:00:00+00:00", "is_draft": False, "head_ref_name": "x", "match_source": "explicit", "confidence": 1.0}
EVIDENCE = {"issue_number": 88, "item_id": "I", "current_status": "In Progress", "has_ignore_label": False, "linked_prs": [MERGED], "open_spec_proposals": [], "last_status_actor": None, "last_status_at": None, "transition_count": 0}


def test_noop_never_comments():
    assert should_comment({"action": "noop", "reason": "x"}) is False
    assert should_comment({"action": "set_done", "reason": "x"}) is True


def test_set_done_cites_merged_pr_and_carries_a_parseable_fingerprint():
    body = build_comment_body({"action": "set_done", "reason": "PR merged, none open"}, EVIDENCE, CTX)
    assert "Done — PR #88 merged 2026-09-14." in body
    assert parse_fingerprint(body) == {"run_id": "run-abc", "decision": "set_done", "evidence_hash": "deadbeef"}


def test_dry_run_is_prefixed_and_invisible_to_fingerprint_parsing():
    body = build_comment_body({"action": "set_done", "reason": "x"}, EVIDENCE, CommentContext(**{**CTX.__dict__, "dry_run": True}))
    assert body.startswith("**[dry run]**")
    assert parse_fingerprint(body) is None
