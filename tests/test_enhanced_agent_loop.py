"""Tests for enhanced_agent_loop.py, derived from
openspec/changes/enhanced-agent-loop/specs/enhanced-agent-loop/spec.md.

Requirement -> what a test needs to assert (task 4.1):
- Provide a real web-search tool via DuckDuckGo: web_search returns AbstractText when present,
  a fallback string when empty. Offline tests mock the HTTP layer for determinism (per
  design.md - a live abstract can change over time); the live section below hits the real API.
- web_search never raises: each failure mode (URLError, TimeoutError, malformed JSON) is caught
  and returned as a typed error string, not raised.
- Validate tool arguments at the dispatch boundary: validate_args rejects a missing/non-string/
  empty/oversized expression or query before the real tool runs; dispatch never calls the real
  tool when validation fails.
- Steer tool ordering with a few-shot example: the constructed messages list carries the fixed
  user/assistant pair before the real user message on every call.
- Run as a standalone script: exercised end-to-end by the live tests at the bottom (skipped
  without ANTHROPIC_API_KEY), which is this repo's chosen way of testing the full lifecycle.
"""

import json
import logging
import os
import urllib.error
from types import SimpleNamespace
from unittest import mock

import pytest

from agent_loop import enhanced_agent_loop as eal


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(block_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=tool_input)


class _ScriptedClient:
    """A fake Anthropic client returning a pre-scripted sequence of responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


# --- calculator: same ast-based approach as agent_loop/tools.py, same assertions ----

def test_calculator_evaluates_arithmetic_expression():
    assert eal.calculator("68000000 / 1000") == {"result": 68000.0}


def test_calculator_rejects_non_arithmetic_expression_without_raising():
    outcome = eal.calculator("__import__('os').system('echo hi')")
    assert "error" in outcome


# --- web_search: happy path, empty-abstract fallback, and every failure mode --------
# (HTTP layer mocked for determinism - see design.md's Risks note on DuckDuckGo results
# varying over time)

def _fake_response(body_bytes):
    resp = mock.Mock()
    resp.read.return_value = body_bytes
    resp.__enter__ = mock.Mock(return_value=resp)
    resp.__exit__ = mock.Mock(return_value=False)
    return resp


def test_web_search_returns_the_abstract_text_when_present():
    body = json.dumps({"AbstractText": "Python is a programming language."}).encode()
    with mock.patch.object(eal.urllib.request, "urlopen", return_value=_fake_response(body)):
        outcome = eal.web_search("Python")
    assert outcome == {"result": "Python is a programming language."}


def test_web_search_returns_fallback_when_abstract_is_empty():
    body = json.dumps({"AbstractText": ""}).encode()
    with mock.patch.object(eal.urllib.request, "urlopen", return_value=_fake_response(body)):
        outcome = eal.web_search("something obscure")
    assert outcome == {"result": "No summary available for 'something obscure'."}


def test_web_search_reports_a_connection_failure_as_an_error_not_an_exception():
    with mock.patch.object(
        eal.urllib.request,
        "urlopen",
        side_effect=urllib.error.URLError("simulated DNS failure"),
    ):
        outcome = eal.web_search("anything")
    assert "error" in outcome
    assert "URLError" in outcome["error"]


def test_web_search_reports_a_timeout_as_an_error_not_an_exception():
    with mock.patch.object(
        eal.urllib.request, "urlopen", side_effect=TimeoutError("simulated timeout")
    ):
        outcome = eal.web_search("anything")
    assert "error" in outcome
    assert "TimeoutError" in outcome["error"]


def test_web_search_reports_malformed_json_as_an_error_not_an_exception():
    with mock.patch.object(
        eal.urllib.request, "urlopen", return_value=_fake_response(b"not json")
    ):
        outcome = eal.web_search("anything")
    assert "error" in outcome
    assert "JSONDecodeError" in outcome["error"]


# Regression test for a /code-review finding: the except clause only covered URLError,
# TimeoutError, and json.JSONDecodeError - missing failure modes like a socket read raising
# ConnectionResetError, or json.loads raising UnicodeDecodeError on a non-UTF-8 body, would
# propagate uncaught past web_search, past dispatch()'s narrower catch tuple, and crash the
# whole loop - violating the spec's "never raises... for any failure mode" requirement. Fix:
# the except clause now catches Exception broadly at this one boundary.

def test_web_search_reports_a_non_utf8_response_body_as_an_error_not_an_exception():
    with mock.patch.object(
        eal.urllib.request, "urlopen", return_value=_fake_response(b"\xff\xfe not utf-8")
    ):
        outcome = eal.web_search("anything")
    assert "error" in outcome


def test_web_search_reports_an_unanticipated_exception_as_an_error_not_an_exception():
    with mock.patch.object(
        eal.urllib.request, "urlopen", side_effect=ConnectionResetError("simulated reset")
    ):
        outcome = eal.web_search("anything")
    assert "error" in outcome
    assert "ConnectionResetError" in outcome["error"]


# --- validate_args / dispatch: malformed input never reaches the real tool ----------

@pytest.mark.parametrize(
    "name,args",
    [
        ("calculator", {}),
        ("calculator", {"expression": 42}),
        ("calculator", {"expression": ""}),
        ("calculator", {"expression": "1" * 300}),
        ("web_search", {}),
        ("web_search", {"query": 5}),
        ("web_search", {"query": ""}),
        ("web_search", {"query": "x" * 600}),
    ],
)
def test_dispatch_returns_a_validation_error_for_malformed_input_instead_of_crashing(
    name, args
):
    outcome = eal.dispatch(name, args)
    assert "error" in outcome


def test_dispatch_never_calls_the_real_tool_when_validation_fails():
    with mock.patch.object(eal, "calculator") as fake_calculator:
        eal.dispatch("calculator", {"expression": ""})
    fake_calculator.assert_not_called()

    with mock.patch.object(eal, "web_search") as fake_web_search:
        eal.dispatch("web_search", {"query": ""})
    fake_web_search.assert_not_called()


def test_dispatch_calls_the_real_tool_when_validation_passes():
    assert eal.dispatch("calculator", {"expression": "2 + 2"}) == {"result": 4}


# --- few-shot example: prepended before the real user message on every call --------

def test_few_shot_example_precedes_the_real_user_message():
    client = _ScriptedClient([SimpleNamespace(stop_reason="end_turn", content=[_text_block("ok")])])

    eal.run_agent_loop(client, "what is the capital of France?")

    messages = client.calls[0]["messages"]
    assert messages[:2] == eal.FEW_SHOT_EXAMPLE
    assert messages[2] == {"role": "user", "content": "what is the capital of France?"}


# --- loop: tool execution, termination, and the safety cap -------------------------

def test_loop_executes_tool_use_and_threads_result_back_to_claude():
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[_tool_use_block("toolu_1", "calculator", {"expression": "2 + 2"})],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[_text_block("4")]),
        ]
    )

    final_text, tool_calls, terminated_via = eal.run_agent_loop(client, "what is 2 + 2?")

    assert final_text == "4"
    assert tool_calls == [{"name": "calculator", "input": {"expression": "2 + 2"}}]
    assert terminated_via == "end_turn"

    second_call_messages = client.calls[1]["messages"]
    assert second_call_messages[-2]["role"] == "assistant"
    assert second_call_messages[-1]["role"] == "user"
    tool_result = second_call_messages[-1]["content"][0]
    assert tool_result == {
        "type": "tool_result",
        "tool_use_id": "toolu_1",
        "content": "4",
        "is_error": False,
    }


def test_loop_terminates_only_on_end_turn_not_on_text_content_type():
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    _text_block("Let me calculate that."),
                    _tool_use_block("toolu_1", "calculator", {"expression": "1 + 1"}),
                ],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[_text_block("2")]),
        ]
    )

    final_text, tool_calls, terminated_via = eal.run_agent_loop(client, "what is 1 + 1?")

    assert len(client.calls) == 2
    assert tool_calls == [{"name": "calculator", "input": {"expression": "1 + 1"}}]
    assert final_text == "2"
    assert terminated_via == "end_turn"


def test_loop_surfaces_a_validation_error_as_an_action_event_without_crashing():
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[_tool_use_block("toolu_1", "calculator", {"expression": ""})],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[_text_block("done")]),
        ]
    )
    events = []

    eal.run_agent_loop(client, "calculate nothing", on_event=events.append)

    action_events = [e for e in events if e["type"] == "action"]
    assert len(action_events) == 1
    assert action_events[0]["is_error"] is True
    assert "invalid expression" in action_events[0]["content"]


def test_loop_enforces_max_iterations_safety_cap_and_logs_warning(caplog):
    responses = [
        SimpleNamespace(
            stop_reason="tool_use",
            content=[_tool_use_block(f"toolu_{i}", "calculator", {"expression": "1 + 1"})],
        )
        for i in range(5)
    ]
    client = _ScriptedClient(responses)

    with caplog.at_level(logging.WARNING):
        final_text, tool_calls, terminated_via = eal.run_agent_loop(
            client, "loop forever", max_iterations=5
        )

    assert len(client.calls) == 5
    assert terminated_via == "max_iterations"
    assert any("MAX_ITERATIONS" in record.message for record in caplog.records)


# --- live acceptance tests (design.md's live-API test strategy) --------------------

@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="requires a live ANTHROPIC_API_KEY"
)
def test_live_france_population_divided_by_1000_completes_with_a_web_search_action():
    import anthropic

    client = anthropic.Anthropic()
    events = []

    final_text, tool_calls, terminated_via = eal.run_agent_loop(
        client,
        "what is France's population, divided by 1000?",
        on_event=events.append,
    )

    assert terminated_via == "end_turn"
    action_events = [e for e in events if e["type"] == "action"]
    assert any(e["name"] == "web_search" and not e["is_error"] for e in action_events)
    assert any(e["name"] == "calculator" for e in action_events)
    assert final_text.strip()


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="requires a live ANTHROPIC_API_KEY"
)
@pytest.mark.parametrize(
    "prompt",
    [
        "What's Japan's population, divided by 100?",
        "Look up the population of Germany and tell me what 1% of it is.",
        "How many people live in Canada? Divide that number by 500.",
    ],
)
def test_live_ambiguous_request_triggers_web_search_before_calculator(prompt):
    import anthropic

    client = anthropic.Anthropic()

    final_text, tool_calls, terminated_via = eal.run_agent_loop(client, prompt)

    assert terminated_via == "end_turn"
    tool_names = [c["name"] for c in tool_calls]
    assert "web_search" in tool_names
    assert "calculator" in tool_names
    assert tool_names.index("web_search") < tool_names.index("calculator")
