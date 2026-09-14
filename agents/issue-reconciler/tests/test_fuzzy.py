from __future__ import annotations

import anthropic
import pytest
from support import FakeAnthropicClient

from issue_reconciler.fuzzy import match_issue_to_prs

ISSUE = {"number": 9, "title": "Add retry logic to the API client"}
CANDIDATES = [
    {"number": 91, "title": "Add retries to api client", "head_ref_name": "add-retries"},
    {"number": 92, "title": "Update README", "head_ref_name": "docs-update"},
]


def test_returns_no_matches_without_calling_the_model_when_there_are_no_candidates():
    client = FakeAnthropicClient(lambda _kwargs: {"matches": []})
    result = match_issue_to_prs(client, ISSUE, [])
    assert result == []
    assert client.messages.call_count == 0


def test_returns_the_parsed_matches_on_a_valid_first_response():
    client = FakeAnthropicClient(lambda _kwargs: {"matches": [{"pr_number": 91, "confidence": 0.92}, {"pr_number": 92, "confidence": 0.02}]})

    result = match_issue_to_prs(client, ISSUE, CANDIDATES)

    assert result == [{"pr_number": 91, "confidence": 0.92}, {"pr_number": 92, "confidence": 0.02}]
    assert client.messages.call_count == 1


def test_retries_once_on_a_malformed_response_then_uses_the_repaired_result():
    calls = {"n": 0}

    def handler(_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"matches": "not-a-list"}
        return {"matches": [{"pr_number": 91, "confidence": 0.8}]}

    client = FakeAnthropicClient(handler)

    result = match_issue_to_prs(client, ISSUE, CANDIDATES)

    assert result == [{"pr_number": 91, "confidence": 0.8}]
    assert client.messages.call_count == 2


def test_treats_two_consecutive_malformed_responses_as_no_match():
    client = FakeAnthropicClient(lambda _kwargs: {"matches": "not-a-list"})

    result = match_issue_to_prs(client, ISSUE, CANDIDATES)

    assert result == []
    assert client.messages.call_count == 2


def test_propagates_a_genuine_api_error_instead_of_treating_it_as_no_match():
    def handler(_kwargs):
        raise anthropic.APIConnectionError(message="network down", request=None)

    client = FakeAnthropicClient(handler)

    with pytest.raises(anthropic.APIConnectionError):
        match_issue_to_prs(client, ISSUE, CANDIDATES)
    assert client.messages.call_count == 1


def test_drops_a_match_for_a_pr_number_the_model_hallucinated_outside_the_candidate_set():
    client = FakeAnthropicClient(lambda _kwargs: {"matches": [{"pr_number": 999, "confidence": 0.9}, {"pr_number": 91, "confidence": 0.7}]})

    result = match_issue_to_prs(client, ISSUE, CANDIDATES)

    assert result == [{"pr_number": 91, "confidence": 0.7}]


def test_rejects_an_out_of_range_confidence_as_malformed():
    client = FakeAnthropicClient(lambda _kwargs: {"matches": [{"pr_number": 91, "confidence": 1.5}]})

    result = match_issue_to_prs(client, ISSUE, CANDIDATES)

    assert result == []
    assert client.messages.call_count == 2
