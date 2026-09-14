from __future__ import annotations

from support import make_sequential_client

from issue_reconciler.api.fetchers.prs import fetch_linked_prs

MERGED_PR = {
    "__typename": "PullRequest",
    "number": 10,
    "title": "Fix issue 1",
    "state": "MERGED",
    "merged": True,
    "mergedAt": "2026-09-14T00:00:00+00:00",
    "isDraft": False,
    "headRefName": "fix-1",
}


def test_includes_a_pr_only_when_the_cross_reference_will_close_the_issue():
    client, _ = make_sequential_client(
        [
            {
                "repository": {
                    "issue_0": {
                        "timelineItems": {
                            "nodes": [
                                {"__typename": "CrossReferencedEvent", "willCloseTarget": True, "source": MERGED_PR},
                                {
                                    "__typename": "CrossReferencedEvent",
                                    "willCloseTarget": False,
                                    "source": {**MERGED_PR, "number": 11},
                                },
                            ]
                        }
                    }
                }
            }
        ]
    )

    result = fetch_linked_prs(client, [1])

    assert result[1] == [
        {
            "number": 10,
            "title": "Fix issue 1",
            "state": "MERGED",
            "merged": True,
            "merged_at": "2026-09-14T00:00:00+00:00",
            "is_draft": False,
            "head_ref_name": "fix-1",
            "match_source": "explicit",
            "confidence": 1.0,
        }
    ]


def test_includes_a_manually_connected_pr_and_ignores_non_pr_sources():
    client, _ = make_sequential_client(
        [
            {
                "repository": {
                    "issue_0": {
                        "timelineItems": {
                            "nodes": [
                                {"__typename": "ConnectedEvent", "subject": {**MERGED_PR, "number": 20}},
                                {"__typename": "ConnectedEvent", "subject": {"__typename": "Issue"}},
                            ]
                        }
                    }
                }
            }
        ]
    )

    result = fetch_linked_prs(client, [1])

    assert len(result[1]) == 1
    assert result[1][0]["number"] == 20


def test_deduplicates_a_pr_referenced_by_multiple_timeline_events():
    client, _ = make_sequential_client(
        [
            {
                "repository": {
                    "issue_0": {
                        "timelineItems": {
                            "nodes": [
                                {"__typename": "CrossReferencedEvent", "willCloseTarget": True, "source": MERGED_PR},
                                {"__typename": "ConnectedEvent", "subject": MERGED_PR},
                            ]
                        }
                    }
                }
            }
        ]
    )

    result = fetch_linked_prs(client, [1])

    assert len(result[1]) == 1


def test_batches_multiple_issues_into_one_request_via_aliases():
    client, calls = make_sequential_client(
        [
            {
                "repository": {
                    "issue_0": {"timelineItems": {"nodes": []}},
                    "issue_1": {
                        "timelineItems": {
                            "nodes": [{"__typename": "ConnectedEvent", "subject": {**MERGED_PR, "number": 30}}]
                        }
                    },
                }
            }
        ]
    )

    result = fetch_linked_prs(client, [5, 8])

    assert len(calls) == 1
    assert result[5] == []
    assert result[8][0]["number"] == 30
