"""Tests for reading what the agent reported back.

The payload shape here matches a real `claude -p --output-format json` result.
"""
from __future__ import annotations

import json

from harness.session import parse_result

SUCCESS = json.dumps(
    {
        "result": "done",
        "is_error": False,
        "total_cost_usd": 0.0242437,
        "num_turns": 1,
        "modelUsage": {"claude-haiku-4-5-20251001": {"inputTokens": 10}},
        "permission_denials": [],
    }
)


def test_reads_the_answer_and_the_accounting():
    result = parse_result(SUCCESS)

    assert result.ok is True
    assert result.text == "done"
    assert result.cost_usd == 0.0242437
    assert result.turns == 1


def test_reports_which_model_actually_served_the_request():
    """The flag says what was asked for; modelUsage says what ran."""
    result = parse_result(SUCCESS)

    assert result.models == ["claude-haiku-4-5-20251001"]


def test_surfaces_tool_calls_the_policy_blocked():
    payload = json.loads(SUCCESS)
    payload["permission_denials"] = [{"tool_name": "Write"}]

    result = parse_result(json.dumps(payload))

    assert len(result.denials) == 1


def test_agent_error_is_not_reported_as_success():
    payload = json.loads(SUCCESS)
    payload["is_error"] = True

    assert parse_result(json.dumps(payload)).ok is False


def test_unparseable_output_fails_rather_than_looking_empty():
    result = parse_result("claude: command not found")

    assert result.ok is False
    assert "parseable JSON" in result.error
