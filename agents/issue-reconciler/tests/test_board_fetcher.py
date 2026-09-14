from __future__ import annotations

from support import make_sequential_client

from issue_reconciler.api.fetchers.board import fetch_board_items


def test_filters_out_items_from_other_repositories_and_paginates():
    client, calls = make_sequential_client(
        [
            {
                "node": {
                    "items": {
                        "pageInfo": {"hasNextPage": True, "endCursor": "CURSOR_1"},
                        "nodes": [
                            {
                                "id": "item-1",
                                "status": {"name": "Todo"},
                                "content": {"__typename": "Issue", "number": 1, "repository": {"name": "ai-on-boarding"}},
                            },
                            {
                                "id": "item-2",
                                "status": {"name": "Done"},
                                "content": {"__typename": "Issue", "number": 2, "repository": {"name": "some-other-repo"}},
                            },
                            {"id": "item-3", "status": None, "content": {"__typename": "PullRequest"}},
                        ],
                    }
                }
            },
            {
                "node": {
                    "items": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "item-4",
                                "status": None,
                                "content": {"__typename": "Issue", "number": 4, "repository": {"name": "ai-on-boarding"}},
                            }
                        ],
                    }
                }
            },
        ]
    )

    items = fetch_board_items(client)

    assert items == [
        {"item_id": "item-1", "issue_number": 1, "status": "Todo"},
        {"item_id": "item-4", "issue_number": 4, "status": None},
    ]
    assert len(calls) == 2
    assert calls[1]["variables"]["cursor"] == "CURSOR_1"
