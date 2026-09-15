from __future__ import annotations

from datetime import datetime, timezone

from support import make_sequential_client

from issue_reconciler.io.github import (
    fetch_board_items,
    fetch_linked_prs,
    fetch_open_issues,
    gather_openspec_proposals,
    summarize_history,
)

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


# ---- board items ---------------------------------------------------------


def test_board_items_filter_other_repos_and_paginate():
    client, calls = make_sequential_client(
        [
            {
                "node": {
                    "items": {
                        "pageInfo": {"hasNextPage": True, "endCursor": "CURSOR_1"},
                        "nodes": [
                            {"id": "item-1", "status": {"name": "Todo"}, "content": {"__typename": "Issue", "number": 1, "repository": {"name": "ai-on-boarding"}}},
                            {"id": "item-2", "status": {"name": "Done"}, "content": {"__typename": "Issue", "number": 2, "repository": {"name": "some-other-repo"}}},
                            {"id": "item-3", "status": None, "content": {"__typename": "PullRequest"}},
                        ],
                    }
                }
            },
            {"node": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [{"id": "item-4", "status": None, "content": {"__typename": "Issue", "number": 4, "repository": {"name": "ai-on-boarding"}}}]}}},
        ]
    )

    items = fetch_board_items(client)

    assert items == [{"item_id": "item-1", "issue_number": 1, "status": "Todo"}, {"item_id": "item-4", "issue_number": 4, "status": None}]
    assert calls[1]["variables"]["cursor"] == "CURSOR_1"


# ---- open issues -----------------------------------------------------------


def test_open_issues_normalize_labels():
    client, _ = make_sequential_client(
        [
            {
                "repository": {
                    "issues": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {"id": "I_1", "number": 1, "title": "Fix the thing", "labels": {"nodes": [{"name": "bug"}, {"name": "agent:ignore"}]}},
                            {"id": "I_2", "number": 2, "title": "Add the other thing", "labels": {"nodes": []}},
                        ],
                    }
                }
            }
        ]
    )

    assert fetch_open_issues(client) == [
        {"id": "I_1", "number": 1, "title": "Fix the thing", "labels": ["bug", "agent:ignore"]},
        {"id": "I_2", "number": 2, "title": "Add the other thing", "labels": []},
    ]


# ---- linked PRs (explicit) --------------------------------------------------

MERGED_PR = {"__typename": "PullRequest", "number": 10, "title": "Fix issue 1", "state": "MERGED", "merged": True, "mergedAt": "2026-09-14T00:00:00+00:00", "isDraft": False, "headRefName": "fix-1"}


def test_linked_prs_includes_any_cross_reference_not_just_closing_keywords():
    # The team's convention requires every PR description to name its
    # issue, but not necessarily with a GitHub closing keyword - a plain
    # "#1" mention still counts (willCloseTarget: False here).
    client, _ = make_sequential_client(
        [{"repository": {"issue_0": {"timelineItems": {"nodes": [
            {"__typename": "CrossReferencedEvent", "willCloseTarget": True, "source": MERGED_PR},
            {"__typename": "CrossReferencedEvent", "willCloseTarget": False, "source": {**MERGED_PR, "number": 11}},
        ]}}}}]
    )

    result = fetch_linked_prs(client, [1])

    assert [pr["number"] for pr in result[1]] == [10, 11]
    assert result[1][0]["title"] == "Fix issue 1"
    assert result[1][0]["merged"] is True


def test_linked_prs_includes_manually_connected_and_ignores_non_pr():
    client, _ = make_sequential_client(
        [{"repository": {"issue_0": {"timelineItems": {"nodes": [
            {"__typename": "ConnectedEvent", "subject": {**MERGED_PR, "number": 20}},
            {"__typename": "ConnectedEvent", "subject": {"__typename": "Issue"}},
        ]}}}}]
    )

    result = fetch_linked_prs(client, [1])
    assert [pr["number"] for pr in result[1]] == [20]


def test_linked_prs_deduplicates_and_batches_via_aliases():
    client, calls = make_sequential_client(
        [{"repository": {
            "issue_0": {"timelineItems": {"nodes": [{"__typename": "CrossReferencedEvent", "willCloseTarget": True, "source": MERGED_PR}, {"__typename": "ConnectedEvent", "subject": MERGED_PR}]}},
            "issue_1": {"timelineItems": {"nodes": [{"__typename": "ConnectedEvent", "subject": {**MERGED_PR, "number": 30}}]}},
        }}]
    )

    result = fetch_linked_prs(client, [5, 8])

    assert len(calls) == 1
    assert len(result[5]) == 1  # deduped
    assert result[8][0]["number"] == 30


# ---- OpenSpec proposals -----------------------------------------------------


def test_openspec_proposals_map_to_every_referenced_issue():
    client, _ = make_sequential_client(
        [
            {"repository": {"object": {"entries": [{"name": "fix-9-and-10", "type": "tree"}, {"name": "unrelated", "type": "tree"}]}}},
            {"repository": {"proposal_0": {"text": "Fixes #9 and #10."}, "proposal_1": {"text": "No reference."}}},
        ]
    )

    result = gather_openspec_proposals(client)

    assert result[9] == ["fix-9-and-10"]
    assert result[10] == ["fix-9-and-10"]
    assert 11 not in result


def test_openspec_proposals_excludes_archive_and_skips_second_query_if_empty():
    client, calls = make_sequential_client([{"repository": {"object": {"entries": [{"name": "archive", "type": "tree"}]}}}])
    assert gather_openspec_proposals(client) == {}
    assert len(calls) == 1


# ---- board history -----------------------------------------------------------


def test_history_no_comments_means_no_actor():
    assert summarize_history([], NOW) == {"last_status_actor": None, "last_status_at": None, "transition_count": 0}


def test_history_fingerprinted_comment_attributed_to_agent_not_pat_owner():
    from issue_reconciler.hashing import build_fingerprint
    from issue_reconciler.rules import AGENT_ACTOR

    fp = build_fingerprint({"run_id": "r1", "decision": "set_in_progress", "evidence_hash": "a"})
    comments = [{"author": "a-human-owned-pat", "body": f"in progress\n{fp}", "created_at": "2026-09-14T09:00:00+00:00"}]

    result = summarize_history(comments, NOW)

    assert result["last_status_actor"] == AGENT_ACTOR
    assert result["transition_count"] == 1


def test_history_human_comment_after_agent_write_overrides_actor():
    from issue_reconciler.hashing import build_fingerprint

    fp = build_fingerprint({"run_id": "r1", "decision": "set_in_progress", "evidence_hash": "a"})
    comments = [
        {"author": "bot", "body": f"automated\n{fp}", "created_at": "2026-09-13T00:00:00+00:00"},
        {"author": "bob", "body": "I am handling this", "created_at": "2026-09-14T08:00:00+00:00"},
    ]

    result = summarize_history(comments, NOW)
    assert result["last_status_actor"] == "bob"
