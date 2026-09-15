from __future__ import annotations

from datetime import datetime, timezone

import anthropic
import pytest

from issue_reconciler.ai.reasoning import activity_check, completion_check, reference_validation, stale_or_superseded_check
from support import FakeAnthropicClient

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
PR = {"number": 1, "title": "Fix the bug", "state": "OPEN", "merged": False, "merged_at": None, "is_draft": False, "head_ref_name": "x", "updated_at": "2026-09-01T00:00:00+00:00", "review_decision": None}


def test_completion_check_returns_the_verdict():
    client = FakeAnthropicClient(lambda _: {"fully_resolved": False, "reasoning": "only handles half the cases"})
    result = completion_check(client, "Fix the bug", [PR])
    assert result == {"fully_resolved": False, "reasoning": "only handles half the cases"}


def test_activity_check_returns_the_verdict():
    client = FakeAnthropicClient(lambda _: {"status": "abandoned", "reasoning": "no activity in 2 weeks"})
    result = activity_check(client, "Fix the bug", PR, NOW)
    assert result["status"] == "abandoned"


def test_reference_validation_returns_the_verdict():
    client = FakeAnthropicClient(lambda _: {"matches": False, "reasoning": "unrelated title"})
    result = reference_validation(client, "Fix the bug", PR)
    assert result["matches"] is False


def test_stale_or_superseded_check_returns_the_verdict():
    client = FakeAnthropicClient(lambda _: {"superseded": True, "reasoning": "PR #2 replaces PR #1's approach"})
    result = stale_or_superseded_check(client, "Fix the bug", [PR, {**PR, "number": 2}])
    assert result["superseded"] is True


def test_malformed_response_retries_once_then_returns_none():
    calls = {"n": 0}

    def handler(_kwargs):
        calls["n"] += 1
        return {"reasoning": "missing the required field"}  # never has fully_resolved

    client = FakeAnthropicClient(handler)
    assert completion_check(client, "Fix the bug", [PR]) is None
    assert calls["n"] == 2


def test_genuine_api_error_propagates():
    def handler(_kwargs):
        raise anthropic.APIConnectionError(message="network down", request=None)

    client = FakeAnthropicClient(handler)
    with pytest.raises(anthropic.APIConnectionError):
        completion_check(client, "Fix the bug", [PR])
