from __future__ import annotations

from datetime import datetime, timezone

from support import make_sequential_client

from issue_reconciler.api.fetchers.candidate_prs import fetch_candidate_prs

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


def _pr(**overrides):
    base = {
        "number": 1,
        "title": "PR",
        "headRefName": "branch",
        "state": "OPEN",
        "isDraft": False,
        "mergedAt": None,
    }
    return {**base, **overrides}


def test_includes_open_prs_and_merges_within_the_lookback_window_excluding_older_merges():
    client, _ = make_sequential_client(
        [
            {
                "repository": {
                    "open": {"nodes": [_pr(number=1, title="WIP feature", headRefName="wip-feature")]},
                    "merged": {
                        "nodes": [
                            _pr(number=2, title="Recent fix", headRefName="recent-fix", state="MERGED", mergedAt="2026-09-10T00:00:00+00:00"),
                            _pr(number=3, title="Old fix", headRefName="old-fix", state="MERGED", mergedAt="2026-08-01T00:00:00+00:00"),
                        ]
                    },
                }
            }
        ]
    )

    result = fetch_candidate_prs(client, NOW)

    assert [c["number"] for c in result] == [1, 2]
    assert result[0]["merged"] is False
    assert result[1]["merged"] is True


def test_deduplicates_a_pr_in_both_the_open_and_merged_pages():
    client, _ = make_sequential_client(
        [
            {
                "repository": {
                    "open": {"nodes": [_pr(number=1, title="Feature", headRefName="feature")]},
                    "merged": {
                        "nodes": [
                            _pr(number=1, title="Feature", headRefName="feature", state="MERGED", mergedAt="2026-09-13T00:00:00+00:00")
                        ]
                    },
                }
            }
        ]
    )

    result = fetch_candidate_prs(client, NOW)

    assert len(result) == 1
