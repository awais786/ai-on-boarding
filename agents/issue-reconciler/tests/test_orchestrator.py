from __future__ import annotations

from datetime import datetime, timedelta, timezone

import anthropic
import pytest
from support import FakeAnthropicClient, make_routed_client

from issue_reconciler import orchestrator
from issue_reconciler.state import acquire_lease

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


def base_routes(**overrides):
    routes = {
        "BoardItems": {"node": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}},
        "OpenIssues": {"repository": {"issues": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}},
        "LinkedPRs": {"repository": {}},
        "IssueComments": {"repository": {}},
        "OpenSpecChangesTree": {"repository": {"object": {"entries": []}}},
        "OpenSpecProposals": {"repository": {}},
        "CandidatePRs": {"repository": {"open": {"nodes": []}, "merged": {"nodes": []}}},
    }
    routes.update(overrides)
    return list(routes.items())


def board_with_one_item(item_id, issue_number, status):
    return {
        "node": {
            "items": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {
                        "id": item_id,
                        "status": {"name": status} if status else None,
                        "content": {"__typename": "Issue", "number": issue_number, "repository": {"name": "ai-on-boarding"}},
                    }
                ],
            }
        }
    }


def open_issues_response(issues):
    return {
        "repository": {
            "issues": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {
                        "id": f"I_{i['number']}",
                        "number": i["number"],
                        "title": i["title"],
                        "labels": {"nodes": [{"name": name} for name in i.get("labels", [])]},
                    }
                    for i in issues
                ],
            }
        }
    }


MERGED_PR_FIELDS = {
    "__typename": "PullRequest",
    "number": 88,
    "title": "Fix bug",
    "state": "MERGED",
    "merged": True,
    "mergedAt": "2026-09-14T00:00:00+00:00",
    "isDraft": False,
    "headRefName": "fix-bug",
}


def test_happy_path_explicit_merged_pr_resolves_to_set_done_and_the_lease_is_released():
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board_with_one_item("PVTI_5", 5, "In Progress"),
            OpenIssues=open_issues_response([{"number": 5, "title": "Fix bug"}]),
            LinkedPRs={"repository": {"issue_0": {"timelineItems": {"nodes": [{"__typename": "ConnectedEvent", "subject": MERGED_PR_FIELDS}]}}}},
        )
    )
    anthropic_client = FakeAnthropicClient(lambda _: {"matches": []})

    result = orchestrator.run(
        github_client=client, anthropic_client=anthropic_client, run_id="run-1", lease_state={}, run_log=[], now=NOW
    )

    assert len(result["processed"]) == 1
    assert result["processed"][0]["decision"] == {"action": "set_done", "reason": "PR merged, none open"}
    assert result["lease_state"] == {}
    assert len(result["run_log"]) == 1
    assert result["circuit_broken"] is False


def test_an_already_leased_issue_is_skipped_and_its_lease_is_left_untouched():
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board_with_one_item("PVTI_5", 5, "Todo"),
            OpenIssues=open_issues_response([{"number": 5, "title": "Fix bug"}]),
        )
    )
    anthropic_client = FakeAnthropicClient(lambda _: {"matches": []})
    pre_leased = acquire_lease({}, 5, 5 * 60, NOW)

    result = orchestrator.run(
        github_client=client, anthropic_client=anthropic_client, run_id="run-1", lease_state=pre_leased, run_log=[], now=NOW
    )

    assert result["processed"][0]["skipped"] == "leased"
    assert result["lease_state"] == pre_leased
    assert len(result["run_log"]) == 0
    assert anthropic_client.messages.call_count == 0


def test_unchanged_evidence_since_the_last_run_is_skipped_with_no_model_call_and_no_new_run_log_entry():
    routes = base_routes(
        BoardItems=board_with_one_item("PVTI_5", 5, "In Progress"),
        OpenIssues=open_issues_response([{"number": 5, "title": "Fix bug"}]),
        LinkedPRs={"repository": {"issue_0": {"timelineItems": {"nodes": [{"__typename": "ConnectedEvent", "subject": MERGED_PR_FIELDS}]}}}},
    )

    client1, _ = make_routed_client(routes)
    first = orchestrator.run(
        github_client=client1, anthropic_client=FakeAnthropicClient(lambda _: {"matches": []}),
        run_id="run-1", lease_state={}, run_log=[], now=NOW,
    )

    client2, _ = make_routed_client(routes)
    anthropic2 = FakeAnthropicClient(lambda _: {"matches": []})
    second = orchestrator.run(
        github_client=client2, anthropic_client=anthropic2,
        run_id="run-2", lease_state={}, run_log=first["run_log"], now=NOW + timedelta(minutes=1),
    )

    assert second["processed"][0]["skipped"] == "unchanged-evidence"
    assert len(second["run_log"]) == len(first["run_log"])
    assert anthropic2.messages.call_count == 0


def test_an_issue_with_no_explicit_pr_reference_is_fuzzy_matched_against_the_candidate_pool():
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board_with_one_item("PVTI_5", 5, "Todo"),
            OpenIssues=open_issues_response([{"number": 5, "title": "Add retries"}]),
            CandidatePRs={
                "repository": {
                    "open": {"nodes": []},
                    "merged": {"nodes": [{"number": 91, "title": "Add retries to client", "headRefName": "add-retries", "state": "MERGED", "isDraft": False, "mergedAt": NOW.isoformat()}]},
                }
            },
        )
    )
    anthropic_client = FakeAnthropicClient(lambda _: {"matches": [{"pr_number": 91, "confidence": 0.9}]})

    result = orchestrator.run(
        github_client=client, anthropic_client=anthropic_client, run_id="run-1", lease_state={}, run_log=[], now=NOW
    )

    assert anthropic_client.messages.call_count == 1
    assert result["processed"][0]["decision"] == {"action": "set_done", "reason": "PR merged, none open"}
    assert result["processed"][0]["evidence"]["linked_prs"][0]["match_source"] == "fuzzy"


def test_an_ignored_issue_never_reaches_the_model():
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board_with_one_item("PVTI_5", 5, "Todo"),
            OpenIssues=open_issues_response([{"number": 5, "title": "Add retries", "labels": ["agent:ignore"]}]),
            CandidatePRs={"repository": {"open": {"nodes": [{"number": 91, "title": "Add retries", "headRefName": "add-retries", "state": "OPEN", "isDraft": False, "mergedAt": None}]}, "merged": {"nodes": []}}},
        )
    )
    anthropic_client = FakeAnthropicClient(lambda _: {"matches": []})

    result = orchestrator.run(
        github_client=client, anthropic_client=anthropic_client, run_id="run-1", lease_state={}, run_log=[], now=NOW
    )

    assert result["processed"][0]["decision"] == {"action": "noop", "reason": "ignore label"}
    assert anthropic_client.messages.call_count == 0


def test_a_board_item_whose_issue_is_not_open_is_excluded_from_processing():
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board_with_one_item("PVTI_9", 9, "Todo"),
            OpenIssues=open_issues_response([{"number": 5, "title": "A different, still-open issue"}]),
        )
    )
    anthropic_client = FakeAnthropicClient(lambda _: {"matches": []})

    result = orchestrator.run(
        github_client=client, anthropic_client=anthropic_client, run_id="run-1", lease_state={}, run_log=[], now=NOW
    )

    assert result["processed"] == []


def test_the_model_call_cap_trips_the_circuit_breaker_before_exhausting_the_batch():
    board = {
        "node": {
            "items": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {"id": "PVTI_1", "status": None, "content": {"__typename": "Issue", "number": 1, "repository": {"name": "ai-on-boarding"}}},
                    {"id": "PVTI_2", "status": None, "content": {"__typename": "Issue", "number": 2, "repository": {"name": "ai-on-boarding"}}},
                ],
            }
        }
    }
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board,
            OpenIssues=open_issues_response([{"number": 1, "title": "Issue one"}, {"number": 2, "title": "Issue two"}]),
            LinkedPRs={"repository": {"issue_0": {"timelineItems": {"nodes": []}}, "issue_1": {"timelineItems": {"nodes": []}}}},
            IssueComments={"repository": {"issue_0": {"comments": {"nodes": []}}, "issue_1": {"comments": {"nodes": []}}}},
            CandidatePRs={"repository": {"open": {"nodes": [{"number": 50, "title": "Some PR", "headRefName": "x", "state": "OPEN", "isDraft": False, "mergedAt": None}]}, "merged": {"nodes": []}}},
        )
    )
    anthropic_client = FakeAnthropicClient(lambda _: {"matches": []})

    result = orchestrator.run(
        github_client=client, anthropic_client=anthropic_client, run_id="run-1", lease_state={}, run_log=[], now=NOW,
        max_concurrency=1, model_call_cap=1,
    )

    assert result["circuit_broken"] is True
    assert len(result["processed"]) == 1


def test_a_failure_rate_above_the_circuit_breaker_threshold_halts_the_rest_of_the_batch():
    issues = [{"number": n, "title": f"Issue {n}"} for n in range(1, 6)]
    board = {
        "node": {
            "items": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {"id": f"PVTI_{i['number']}", "status": None, "content": {"__typename": "Issue", "number": i["number"], "repository": {"name": "ai-on-boarding"}}}
                    for i in issues
                ],
            }
        }
    }
    linked_prs_response = {"repository": {f"issue_{i}": {"timelineItems": {"nodes": []}} for i in range(len(issues))}}
    comments_response = {"repository": {f"issue_{i}": {"comments": {"nodes": []}} for i in range(len(issues))}}

    client, _ = make_routed_client(
        base_routes(
            BoardItems=board,
            OpenIssues=open_issues_response(issues),
            LinkedPRs=linked_prs_response,
            IssueComments=comments_response,
            CandidatePRs={"repository": {"open": {"nodes": [{"number": 50, "title": "Some PR", "headRefName": "x", "state": "OPEN", "isDraft": False, "mergedAt": None}]}, "merged": {"nodes": []}}},
        )
    )

    def handler(_kwargs):
        raise anthropic.APIConnectionError(message="model outage", request=None)

    anthropic_client = FakeAnthropicClient(handler)

    result = orchestrator.run(
        github_client=client, anthropic_client=anthropic_client, run_id="run-1", lease_state={}, run_log=[], now=NOW,
        max_concurrency=1,
    )

    assert result["circuit_broken"] is True
    assert len(result["failed"]) == 2
    assert len(result["processed"]) == 0


def test_validate_board_config_resolves_quietly_when_project_exists():
    client, _ = make_routed_client([("ValidateProject", {"node": {"id": "PVT_kwHOA4V_f84AGZiK"}})])
    orchestrator.validate_board_config(client)  # does not raise


def test_validate_board_config_fails_loudly_when_project_no_longer_resolves():
    client, _ = make_routed_client([("ValidateProject", {"node": None})])
    with pytest.raises(RuntimeError, match="no longer resolves"):
        orchestrator.validate_board_config(client)
