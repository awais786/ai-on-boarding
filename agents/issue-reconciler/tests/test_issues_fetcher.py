from __future__ import annotations

from support import make_sequential_client

from issue_reconciler.api.fetchers.issues import fetch_open_issues


def test_normalizes_open_issues_with_their_labels():
    client, _ = make_sequential_client(
        [
            {
                "repository": {
                    "issues": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "I_1",
                                "number": 1,
                                "title": "Fix the thing",
                                "labels": {"nodes": [{"name": "bug"}, {"name": "agent:ignore"}]},
                            },
                            {"id": "I_2", "number": 2, "title": "Add the other thing", "labels": {"nodes": []}},
                        ],
                    }
                }
            }
        ]
    )

    issues = fetch_open_issues(client)

    assert issues == [
        {"id": "I_1", "number": 1, "title": "Fix the thing", "labels": ["bug", "agent:ignore"]},
        {"id": "I_2", "number": 2, "title": "Add the other thing", "labels": []},
    ]
