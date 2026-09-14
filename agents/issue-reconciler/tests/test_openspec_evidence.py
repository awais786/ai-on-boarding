from __future__ import annotations

from support import make_sequential_client

from issue_reconciler.spokes.openspec_evidence import gather_openspec_proposals


def test_maps_a_proposal_to_every_issue_it_references():
    client, _ = make_sequential_client(
        [
            {
                "repository": {
                    "object": {
                        "entries": [
                            {"name": "fix-9-and-10", "type": "tree"},
                            {"name": "unrelated-change", "type": "tree"},
                        ]
                    }
                }
            },
            {
                "repository": {
                    "proposal_0": {"text": "Fixes #9 and #10 in one pass."},
                    "proposal_1": {"text": "No issue reference here."},
                }
            },
        ]
    )

    result = gather_openspec_proposals(client)

    assert result[9] == ["fix-9-and-10"]
    assert result[10] == ["fix-9-and-10"]
    assert 11 not in result


def test_does_not_duplicate_an_issue_reference_mentioned_twice_in_the_same_proposal():
    client, _ = make_sequential_client(
        [
            {"repository": {"object": {"entries": [{"name": "fix-9-twice", "type": "tree"}]}}},
            {"repository": {"proposal_0": {"text": "Fixes #9. See also #9 for context."}}},
        ]
    )

    result = gather_openspec_proposals(client)

    assert result[9] == ["fix-9-twice"]
