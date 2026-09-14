from __future__ import annotations

from support import make_sequential_client

from issue_reconciler.api.fetchers.timeline import fetch_issue_comments


def test_normalizes_comments_and_batches_multiple_issues_into_one_request():
    client, calls = make_sequential_client(
        [
            {
                "repository": {
                    "issue_0": {
                        "comments": {
                            "nodes": [{"author": {"login": "alice"}, "body": "looks good", "createdAt": "2026-09-14T00:00:00+00:00"}]
                        }
                    },
                    "issue_1": {
                        "comments": {
                            "nodes": [{"author": None, "body": "deleted user comment", "createdAt": "2026-09-13T00:00:00+00:00"}]
                        }
                    },
                }
            }
        ]
    )

    result = fetch_issue_comments(client, [1, 2])

    assert len(calls) == 1
    assert result[1] == [{"author": "alice", "body": "looks good", "created_at": "2026-09-14T00:00:00+00:00"}]
    assert result[2] == [{"author": None, "body": "deleted user comment", "created_at": "2026-09-13T00:00:00+00:00"}]
