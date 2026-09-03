"""Tests for the loop, written from specs/multi-tool-agent-loop/spec.md."""

from __future__ import annotations

import logging

import pytest

from agent_loop.loop import IterationLimitExceeded, UnusableResponse, run
from agent_loop.tests.conftest import (
    StubClient,
    finished,
    requesting,
    response,
    text_block,
    thinking_block,
    tool_use_block,
)

SEARCH = tool_use_block("web_search", {"query": "population of Tokyo"}, id="search-1")
CALCULATE = tool_use_block("calculator", {"expression": "14180000 / 1000"}, id="calc-1")


# --- Requirement: Terminate only on the model's reported stop reason --------------------------


def test_a_response_that_leads_with_text_but_requests_a_tool_continues_the_loop():
    """The first content block being text must not be read as the model having finished."""
    client = StubClient(
        requesting(text_block("Let me look that up."), SEARCH),
        finished("14180"),
    )
    assert run("q", client=client, model="m") == "14180"
    assert len(client.requests) == 2


def test_wording_that_sounds_final_does_not_end_the_loop():
    """Only the stop reason ends a run - never what the model happened to write."""
    client = StubClient(
        requesting(text_block("I'm done. All finished!"), SEARCH),
        finished("actually the answer"),
    )
    assert run("q", client=client, model="m") == "actually the answer"


def test_the_loop_returns_the_text_when_the_model_reports_it_has_finished():
    client = StubClient(finished("the answer"))
    assert run("q", client=client, model="m") == "the answer"


def test_a_finished_response_with_several_text_blocks_returns_all_of_them():
    client = StubClient(response("end_turn", [text_block("first"), text_block("second")]))
    assert run("q", client=client, model="m") == "first\nsecond"


# --- Requirement: Thread results back into the conversation -----------------------------------


def test_the_models_response_is_added_to_the_conversation_whole():
    """Reasoning produced alongside a tool request must be returned unchanged."""
    reasoning = thinking_block("", signature="sig-abc")
    content = [reasoning, text_block("looking it up"), SEARCH]
    client = StubClient(response("tool_use", content), finished())

    run("q", client=client, model="m")

    assistant_turn = client.conversation[1]
    assert assistant_turn["role"] == "assistant"
    assert assistant_turn["content"] == content
    assert reasoning in assistant_turn["content"]


def test_every_result_for_one_response_is_returned_in_a_single_turn():
    two = requesting(
        tool_use_block("calculator", {"expression": "1 + 1"}, id="a"),
        tool_use_block("calculator", {"expression": "2 + 2"}, id="b"),
    )
    client = StubClient(two, finished())

    run("q", client=client, model="m")

    user_turns = [m for m in client.conversation if m["role"] == "user"]
    assert len(user_turns) == 2  # the original prompt, then one turn carrying both results
    assert [r["tool_use_id"] for r in user_turns[1]["content"]] == ["a", "b"]


# --- Requirement: Execute every requested tool and return its result --------------------------


def test_a_result_is_returned_against_the_request_it_answers():
    client = StubClient(requesting(CALCULATE), finished())

    run("q", client=client, model="m")

    result = client.conversation[2]["content"][0]
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "calc-1"
    assert result["content"] == "14180"
    assert result["is_error"] is False


def test_a_tool_that_cannot_run_returns_an_error_to_the_model_and_the_loop_continues():
    client = StubClient(
        requesting(tool_use_block("no_such_tool", {"anything": 1}, id="bad-1")),
        finished("recovered"),
    )

    assert run("q", client=client, model="m") == "recovered"

    result = client.conversation[2]["content"][0]
    assert result["is_error"] is True
    assert result["tool_use_id"] == "bad-1"


# --- Requirement: Support several tool calls in sequence --------------------------------------


def test_a_value_found_by_one_tool_is_carried_into_the_next_call():
    client = StubClient(requesting(SEARCH), requesting(CALCULATE), finished("14180"))

    assert run("q", client=client, model="m") == "14180"

    assert len(client.requests) == 3
    search_result = client.requests[1]["messages"][2]["content"][0]["content"]
    assert "14180000" in search_result
    calculated = client.requests[2]["messages"][4]["content"][0]["content"]
    assert calculated == "14180"


# --- Requirement: Cap the number of iterations for safety -------------------------------------


def test_a_normal_run_finishes_well_before_the_safety_cap():
    client = StubClient(requesting(SEARCH), requesting(CALCULATE), finished("14180"))
    run("q", client=client, model="m")
    assert len(client.requests) == 3


def test_reaching_the_safety_cap_records_a_warning(caplog):
    client = StubClient(*[requesting(CALCULATE) for _ in range(20)])
    with caplog.at_level(logging.WARNING, logger="agent_loop.loop"):
        with pytest.raises(IterationLimitExceeded):
            run("q", client=client, model="m", max_iterations=20)
    assert any(r.levelno == logging.WARNING and "safety cap" in r.message for r in caplog.records)


def test_a_capped_run_cannot_be_received_as_though_it_had_finished():
    """A caller must be unable to mistake giving up for an answer."""
    client = StubClient(*[requesting(CALCULATE) for _ in range(5)])
    with pytest.raises(IterationLimitExceeded):
        run("q", client=client, model="m", max_iterations=5)
    assert len(client.requests) == 5


def test_the_cap_is_twenty_iterations_by_default():
    from agent_loop.loop import MAX_ITERATIONS

    assert MAX_ITERATIONS == 20


# --- Requirement: Report a response the loop cannot act on ------------------------------------


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal", "pause_turn", "stop_sequence"])
def test_an_unrecognised_stop_reason_is_reported_rather_than_returned(stop_reason):
    client = StubClient(response(stop_reason, [text_block("partial")]))
    with pytest.raises(UnusableResponse) as raised:
        run("q", client=client, model="m")
    assert stop_reason in str(raised.value)


def test_a_tool_request_naming_no_tool_is_reported():
    client = StubClient(response("tool_use", [text_block("I meant to call something")]))
    with pytest.raises(UnusableResponse):
        run("q", client=client, model="m")


def test_no_turn_is_sent_back_when_a_tool_request_names_no_tool():
    """An empty turn is rejected outright, so the loop must not send one."""
    client = StubClient(response("tool_use", [text_block("nothing here")]))
    with pytest.raises(UnusableResponse):
        run("q", client=client, model="m")
    assert len(client.requests) == 1
