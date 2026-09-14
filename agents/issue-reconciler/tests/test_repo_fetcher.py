from __future__ import annotations

from support import make_sequential_client

from issue_reconciler.api.fetchers.repo import fetch_openspec_changes


def test_excludes_the_archive_directory_and_non_tree_entries():
    client, calls = make_sequential_client(
        [
            {
                "repository": {
                    "object": {
                        "entries": [
                            {"name": "add-issue-9-fix", "type": "tree"},
                            {"name": "archive", "type": "tree"},
                            {"name": "README.md", "type": "blob"},
                        ]
                    }
                }
            },
            {"repository": {"proposal_0": {"text": "Closes #9. Adds the fix."}}},
        ]
    )

    changes = fetch_openspec_changes(client)

    assert changes == [{"name": "add-issue-9-fix", "proposal_text": "Closes #9. Adds the fix."}]
    assert len(calls) == 2


def test_truncates_a_proposal_body_longer_than_max_text_length():
    long_text = "x" * 2000
    client, _ = make_sequential_client(
        [
            {"repository": {"object": {"entries": [{"name": "big-change", "type": "tree"}]}}},
            {"repository": {"proposal_0": {"text": long_text}}},
        ]
    )

    changes = fetch_openspec_changes(client)

    assert len(changes[0]["proposal_text"]) == 500


def test_returns_empty_list_without_a_second_request_when_there_are_no_changes():
    client, calls = make_sequential_client([{"repository": {"object": {"entries": []}}}])

    changes = fetch_openspec_changes(client)

    assert changes == []
    assert len(calls) == 1
