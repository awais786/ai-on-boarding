from __future__ import annotations

from datetime import datetime, timezone

import pytest
from support import make_routed_client

from issue_reconciler.hashing import parse_fingerprint
from issue_reconciler.writers import (
    CommentContext,
    build_comment_body,
    mutate,
    post_comment,
    should_comment,
)

CTX = CommentContext(run_id="run-abc", evidence_hash="deadbeef", logs_url="https://x/logs", now=datetime(2026, 9, 14, 17, 32, tzinfo=timezone.utc), dry_run=False)
MERGED = {"number": 88, "title": "x", "state": "MERGED", "merged": True, "merged_at": "2026-09-14T00:00:00+00:00", "is_draft": False, "head_ref_name": "x"}
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


def test_post_comment_returns_the_new_comment_id():
    client, calls = make_routed_client([("AddComment", {"addComment": {"commentEdge": {"node": {"id": "IC_1"}}}})])
    assert post_comment(client, "I_88", "hello") == "IC_1"
    assert calls[0]["variables"] == {"subjectId": "I_88", "body": "hello"}


def test_set_done_updates_status_then_closes_the_issue():
    client, calls = make_routed_client(
        [
            ("CurrentStatus", {"node": {"status": {"name": "In Progress"}}}),
            ("SetStatus", {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_1"}}}),
            ("CloseIssue", {"closeIssue": {"issue": {"id": "I_1"}}}),
        ]
    )
    mutate(client, "PVTI_1", "I_1", {"action": "set_done", "reason": "x"}, expected_status="In Progress")
    assert len(calls) == 3


def test_flag_looks_up_the_label_then_adds_it():
    client, calls = make_routed_client(
        [
            ("CurrentStatus", {"node": {"status": {"name": "Todo"}}}),
            ("FindLabel", {"repository": {"label": {"id": "LA_1"}}}),
            ("AddLabel", {"addLabelsToLabelable": {"clientMutationId": None}}),
        ]
    )
    mutate(client, "PVTI_1", "I_1", {"action": "flag", "reason": "mixed PR states"}, expected_status="Todo")
    assert len(calls) == 3


def test_flag_raises_a_clean_error_when_the_label_does_not_exist():
    """GraphQL returns {"label": null} (key present, value None) when a label
    lookup misses - not a missing key - so a plain .get("label", {}) default
    never kicks in and used to crash with AttributeError instead of this
    RuntimeError.
    """
    client, _ = make_routed_client([("FindLabel", {"repository": {"label": None}})])
    with pytest.raises(RuntimeError, match="does not exist"):
        mutate(client, None, "I_1", {"action": "flag", "reason": "x"}, expected_status=None)


def test_mutation_skipped_if_status_moved_since_evidence_gathered():
    client, calls = make_routed_client([("CurrentStatus", {"node": {"status": {"name": "Done"}}})])
    mutate(client, "PVTI_1", "I_1", {"action": "set_in_progress", "reason": "x"}, expected_status="Todo")
    assert len(calls) == 1  # only the re-read; no mutation followed


def test_set_done_off_board_skips_status_and_still_closes():
    client, calls = make_routed_client([("CloseIssue", {"closeIssue": {"issue": {"id": "I_1"}}})])
    mutate(client, None, "I_1", {"action": "set_done", "reason": "x"}, expected_status=None)
    assert len(calls) == 1
    assert calls[0]["query"].startswith("mutation CloseIssue")


def test_set_done_off_board_propagates_a_close_failure():
    """Off-board, current_status is always None, so a failed close has no
    self-healing signal (unlike on-board, where the status field forces a
    retry via the evidence hash) - the error must propagate so the caller
    knows this issue's write didn't fully succeed.
    """

    def raise_error(_variables):
        raise RuntimeError("close failed")

    client, _ = make_routed_client([("CloseIssue", raise_error)])
    with pytest.raises(RuntimeError, match="close failed"):
        mutate(client, None, "I_1", {"action": "set_done", "reason": "x"}, expected_status=None)


def test_set_done_on_board_still_swallows_a_close_failure():
    """On-board, current_status flipping to Done is enough to force a retry
    next run via the evidence hash, so a close failure here stays swallowed
    - this is the one case where "the board is already correct" holds.
    """

    def raise_error(_variables):
        raise RuntimeError("close failed")

    client, calls = make_routed_client(
        [
            ("CurrentStatus", {"node": {"status": {"name": "In Progress"}}}),
            ("SetStatus", {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_1"}}}),
            ("CloseIssue", raise_error),
        ]
    )
    mutate(client, "PVTI_1", "I_1", {"action": "set_done", "reason": "x"}, expected_status="In Progress")
    assert len(calls) >= 2  # CurrentStatus + SetStatus ran; close was attempted and swallowed


def test_set_in_progress_off_board_is_a_complete_no_op():
    client, calls = make_routed_client([])
    mutate(client, None, "I_1", {"action": "set_in_progress", "reason": "x"}, expected_status=None)
    assert len(calls) == 0


def test_flag_off_board_still_adds_the_label():
    client, calls = make_routed_client(
        [
            ("FindLabel", {"repository": {"label": {"id": "LA_1"}}}),
            ("AddLabel", {"addLabelsToLabelable": {"clientMutationId": None}}),
        ]
    )
    mutate(client, None, "I_1", {"action": "flag", "reason": "mixed PR states"}, expected_status=None)
    assert len(calls) == 2
