from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from support import FakeAnthropicClient, make_routed_client

from issue_reconciler import orchestrator
from issue_reconciler.orchestrator import _RunState
from issue_reconciler.state import acquire_lease

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


def _ok_anthropic_client():
    """A verdict shaped to satisfy every reasoning spoke's schema at once -
    tests that aren't about verdict downgrading use this so a decision
    passes through apply_verdicts unchanged.
    """
    return FakeAnthropicClient(
        lambda _: {"fully_resolved": True, "matches": True, "superseded": False, "status": "active", "reasoning": "ok"}
    )


def base_routes(**overrides):
    routes = {
        "BoardItems": {"node": {"items": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}},
        "OpenIssues": {"repository": {"issues": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}}},
        "LinkedPRs": {"repository": {}},
        "IssueComments": {"repository": {}},
        "OpenSpecChangesTree": {"repository": {"object": {"entries": []}}},
        "OpenSpecProposals": {"repository": {}},
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
    "repository": {"nameWithOwner": "awais786/ai-on-boarding"},
}


def test_happy_path_explicit_merged_pr_resolves_to_set_done_and_the_lease_is_released():
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board_with_one_item("PVTI_5", 5, "In Progress"),
            OpenIssues=open_issues_response([{"number": 5, "title": "Fix bug"}]),
            LinkedPRs={"repository": {"issue_0": {"timelineItems": {"nodes": [{"__typename": "ConnectedEvent", "subject": MERGED_PR_FIELDS}]}}}},
        )
    )

    result = orchestrator.run(github_client=client, anthropic_client=_ok_anthropic_client(), run_id="run-1", lease_state={}, run_log=[], now=NOW)

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
    pre_leased = acquire_lease({}, 5, 5 * 60, NOW)

    result = orchestrator.run(github_client=client, anthropic_client=_ok_anthropic_client(), run_id="run-1", lease_state=pre_leased, run_log=[], now=NOW)

    assert result["processed"][0]["skipped"] == "leased"
    assert result["lease_state"] == pre_leased
    assert len(result["run_log"]) == 0


def test_unchanged_evidence_since_the_last_run_is_skipped():
    routes = base_routes(
        BoardItems=board_with_one_item("PVTI_5", 5, "In Progress"),
        OpenIssues=open_issues_response([{"number": 5, "title": "Fix bug"}]),
        LinkedPRs={"repository": {"issue_0": {"timelineItems": {"nodes": [{"__typename": "ConnectedEvent", "subject": MERGED_PR_FIELDS}]}}}},
    )

    client1, _ = make_routed_client(routes)
    first = orchestrator.run(github_client=client1, anthropic_client=_ok_anthropic_client(), run_id="run-1", lease_state={}, run_log=[], now=NOW)

    client2, _ = make_routed_client(routes)
    second = orchestrator.run(
        github_client=client2, anthropic_client=_ok_anthropic_client(), run_id="run-2", lease_state={}, run_log=first["run_log"], now=NOW + timedelta(minutes=1)
    )

    assert second["processed"][0]["skipped"] == "unchanged-evidence"
    assert len(second["run_log"]) == len(first["run_log"])


def test_an_ignored_issue_is_a_noop():
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board_with_one_item("PVTI_5", 5, "Todo"),
            OpenIssues=open_issues_response([{"number": 5, "title": "Add retries", "labels": ["agent:ignore"]}]),
            LinkedPRs={"repository": {"issue_0": {"timelineItems": {"nodes": [{"__typename": "ConnectedEvent", "subject": MERGED_PR_FIELDS}]}}}},
        )
    )

    result = orchestrator.run(github_client=client, anthropic_client=_ok_anthropic_client(), run_id="run-1", lease_state={}, run_log=[], now=NOW)

    assert result["processed"][0]["decision"] == {"action": "noop", "reason": "ignore label"}


def test_a_board_item_whose_issue_is_not_open_is_ignored_but_the_open_issue_is_still_processed():
    """Board items are optional context, not a gate: a stale board item for
    issue #9 (no longer open) is simply unused, while issue #5 - open but
    never added to the board - is still processed with item_id=None.
    """
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board_with_one_item("PVTI_9", 9, "Todo"),
            OpenIssues=open_issues_response([{"number": 5, "title": "A different, still-open issue"}]),
        )
    )

    result = orchestrator.run(github_client=client, anthropic_client=_ok_anthropic_client(), run_id="run-1", lease_state={}, run_log=[], now=NOW)

    assert len(result["processed"]) == 1
    assert result["processed"][0]["issue_number"] == 5
    assert result["processed"][0]["evidence"]["item_id"] is None
    assert result["processed"][0]["evidence"]["current_status"] is None


def test_run_state_trips_the_circuit_breaker_when_failure_rate_exceeds_threshold():
    state = _RunState({}, [])
    state.add_failed({"issue_number": 1, "error": "x"}, error_rate_threshold=0.2, total=5)
    assert state.circuit_broken is False
    state.add_failed({"issue_number": 2, "error": "x"}, error_rate_threshold=0.2, total=5)
    assert state.circuit_broken is True


def test_validate_board_config_resolves_quietly_when_project_exists():
    client, _ = make_routed_client([("ValidateProject", {"node": {"id": "PVT_kwHOA4V_f84AGZiK"}})])
    orchestrator.validate_board_config(client)  # does not raise


def test_validate_board_config_fails_loudly_when_project_no_longer_resolves():
    client, _ = make_routed_client([("ValidateProject", {"node": None})])
    with pytest.raises(RuntimeError, match="no longer resolves"):
        orchestrator.validate_board_config(client)


def test_a_completion_verdict_can_downgrade_set_done_to_flag():
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board_with_one_item("PVTI_5", 5, "In Progress"),
            OpenIssues=open_issues_response([{"number": 5, "title": "Fix bug"}]),
            LinkedPRs={"repository": {"issue_0": {"timelineItems": {"nodes": [{"__typename": "ConnectedEvent", "subject": MERGED_PR_FIELDS}]}}}},
        )
    )
    anthropic_client = FakeAnthropicClient(lambda _: {"fully_resolved": False, "matches": True, "reasoning": "only half the cases"})

    result = orchestrator.run(github_client=client, anthropic_client=anthropic_client, run_id="run-1", lease_state={}, run_log=[], now=NOW)

    assert result["processed"][0]["decision"]["action"] == "flag"


def test_an_issue_off_the_board_with_a_merged_pr_still_resolves_to_set_done():
    client, _ = make_routed_client(
        base_routes(
            OpenIssues=open_issues_response([{"number": 5, "title": "Fix bug"}]),
            LinkedPRs={"repository": {"issue_0": {"timelineItems": {"nodes": [{"__typename": "ConnectedEvent", "subject": MERGED_PR_FIELDS}]}}}},
        )
    )

    result = orchestrator.run(github_client=client, anthropic_client=_ok_anthropic_client(), run_id="run-1", lease_state={}, run_log=[], now=NOW)

    assert result["processed"][0]["decision"] == {"action": "set_done", "reason": "PR merged, none open"}
    assert result["processed"][0]["evidence"]["item_id"] is None


def test_reasoning_spokes_are_not_called_without_a_linked_pr():
    client, _ = make_routed_client(
        base_routes(
            BoardItems=board_with_one_item("PVTI_5", 5, "Todo"),
            OpenIssues=open_issues_response([{"number": 5, "title": "Fix bug"}]),
        )
    )
    anthropic_client = _ok_anthropic_client()

    result = orchestrator.run(github_client=client, anthropic_client=anthropic_client, run_id="run-1", lease_state={}, run_log=[], now=NOW)

    assert result["processed"][0]["decision"] == {"action": "noop", "reason": "no evidence"}
    assert anthropic_client.messages.call_count == 0
