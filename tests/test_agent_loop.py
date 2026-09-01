"""Tests for the multi-tool agent loop, derived from
openspec/changes/42-multi-tool-claude-agent-loop/specs/multi-tool-agent-loop/spec.md.

Requirement -> what a test needs to assert (task 4.1):
- Register a calculator tool: TOOLS declares name/description/input_schema requiring
  `expression` (string); evaluates arithmetic; returns an error result (not a raised
  exception) for non-arithmetic input or division by zero.
- Register a web-search tool: TOOLS declares name/description/input_schema requiring
  `query` (string); returns a mock result for a known query and a fallback otherwise.
- Execute a requested tool and return its result: on stop_reason == "tool_use", the loop
  executes the named tool, appends Claude's assistant message and a user message with the
  tool_result to the conversation, and sends it back.
- Terminate only on end_turn: the loop must not stop on a text content block accompanying
  a tool_use response; it must stop only when stop_reason == "end_turn".
- Support multiple sequential tool calls: two different tools used back-to-back before
  end_turn.
- Enforce a maximum iteration safety cap: stops after `max_iterations` round trips without
  end_turn, logs a warning, and does not make a further request.
- The France-population example itself is exercised against the live API (see the test at
  the bottom), since it is this repo's chosen way of exercising the full lifecycle
  end-to-end rather than through a scripted fake client.
"""

import logging
import os
from types import SimpleNamespace

import pytest

from agent_loop import tools
from agent_loop.__main__ import _print_event
from agent_loop.loop import MAX_ITERATIONS, run_agent_loop


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


# --- calculator tool ---------------------------------------------------------------

def test_calculator_tool_schema_declares_name_description_and_expression_input():
    schema = next(t for t in tools.TOOLS if t["name"] == "calculator")
    assert schema["name"] == "calculator"
    assert schema["description"]
    assert schema["input_schema"]["required"] == ["expression"]
    assert schema["input_schema"]["properties"]["expression"]["type"] == "string"


def test_calculator_evaluates_arithmetic_expression():
    assert tools.dispatch("calculator", {"expression": "68000000 * 0.10"}) == {
        "result": 6800000.0
    }


def test_calculator_rejects_non_arithmetic_expression_without_raising():
    outcome = tools.dispatch(
        "calculator", {"expression": "__import__('os').system('echo hi')"}
    )
    assert "error" in outcome


def test_calculator_reports_division_by_zero_as_error_not_exception():
    assert tools.dispatch("calculator", {"expression": "1 / 0"}) == {
        "error": "division by zero"
    }


# Regression tests for a /code-review round-2 finding: a syntactically valid but huge
# expression could raise an uncaught OverflowError (converting a giant integer literal to
# float) or RecursionError (a very deep AST from thousands of chained operators), crashing
# the loop instead of returning {"error": ...}. Fix: evaluate_expression() rejects
# expressions over a fixed length before evaluating them - both cases below are caught by
# that length cap, not by the ArithmeticError/RecursionError handlers (which exist as
# defense in depth for a shorter expression that still overflows or recurses too deeply).

def test_calculator_rejects_expression_over_the_length_cap_before_it_can_overflow():
    outcome = tools.dispatch(
        "calculator", {"expression": "1" + "0" * 400 + " * 1.5"}
    )
    assert outcome == {"error": "expression too long (max 200 characters)"}


def test_calculator_rejects_expression_over_the_length_cap_before_it_can_recurse():
    outcome = tools.dispatch("calculator", {"expression": "+".join(["1"] * 5000)})
    assert outcome == {"error": "expression too long (max 200 characters)"}


# Regression test for a /code-review finding: a short expression under the length cap can
# still overflow float range via Python's own literal parsing (ast.parse() folds an
# out-of-range scientific-notation literal to inf before evaluate_expression() ever sees
# it), which the length cap and the ArithmeticError handler both miss since no exception is
# raised. Fix: evaluate_expression() rejects a non-finite result after evaluation.

def test_calculator_rejects_expression_that_evaluates_to_a_non_finite_result():
    outcome = tools.dispatch("calculator", {"expression": "1e400"})
    assert "error" in outcome


# --- web_search tool ----------------------------------------------------------------

def test_web_search_tool_schema_declares_name_description_and_query_input():
    schema = next(t for t in tools.TOOLS if t["name"] == "web_search")
    assert schema["name"] == "web_search"
    assert schema["description"]
    assert schema["input_schema"]["required"] == ["query"]
    assert schema["input_schema"]["properties"]["query"]["type"] == "string"


def test_web_search_returns_mock_result_for_known_query():
    outcome = tools.dispatch("web_search", {"query": "France population"})
    assert "68 million" in outcome["result"]


def test_web_search_returns_fallback_for_unmatched_query():
    outcome = tools.dispatch("web_search", {"query": "something nobody asked about"})
    assert "No mock results" in outcome["result"]


# --- dispatch: malformed tool_input never crashes the loop --------------------------
# Regression test for a /code-review finding: dispatch() was calling each tool's handler
# unguarded, so a tool_use block missing a required field, or supplying the wrong type,
# raised a raw KeyError/TypeError/AttributeError instead of the {"error": ...} result
# design.md and dispatch()'s own docstring promise.

@pytest.mark.parametrize(
    "name,tool_input",
    [
        ("calculator", {}),
        ("calculator", {"expression": 42}),
        ("web_search", {}),
        ("web_search", {"query": 5}),
    ],
)
def test_dispatch_returns_error_result_for_malformed_input_instead_of_raising(
    name, tool_input
):
    outcome = tools.dispatch(name, tool_input)
    assert "error" in outcome


# --- loop: tool execution and result threading ---------------------------------------

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

    final_text, tool_calls, terminated_via = run_agent_loop(
        client, [{"role": "user", "content": "what is 2 + 2?"}]
    )

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

    final_text, tool_calls, terminated_via = run_agent_loop(
        client, [{"role": "user", "content": "what is 1 + 1?"}]
    )

    assert len(client.calls) == 2
    assert tool_calls == [{"name": "calculator", "input": {"expression": "1 + 1"}}]
    assert final_text == "2"
    assert terminated_via == "end_turn"


def test_loop_supports_multiple_sequential_tool_calls():
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    _tool_use_block("toolu_1", "web_search", {"query": "France population"})
                ],
            ),
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    _tool_use_block(
                        "toolu_2", "calculator", {"expression": "68000000 * 0.10"}
                    )
                ],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[_text_block("6.8 million")]),
        ]
    )

    final_text, tool_calls, terminated_via = run_agent_loop(
        client, [{"role": "user", "content": "Find France population and calculate 10%."}]
    )

    assert [c["name"] for c in tool_calls] == ["web_search", "calculator"]
    assert final_text == "6.8 million"
    assert terminated_via == "end_turn"
    assert len(client.calls) == 3


# --- loop: multiple tool_use blocks in one turn are labeled as requested together -----

def test_loop_annotates_tool_use_events_with_batch_position_when_requested_together():
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    _tool_use_block("toolu_1", "web_search", {"query": "France population"}),
                    _tool_use_block("toolu_2", "calculator", {"expression": "1 + 1"}),
                ],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[_text_block("done")]),
        ]
    )
    events = []

    run_agent_loop(
        client, [{"role": "user", "content": "do two things"}], on_event=events.append
    )

    tool_use_events = [e for e in events if e["type"] == "tool_use"]
    assert [(e["batch_index"], e["batch_size"]) for e in tool_use_events] == [(1, 2), (2, 2)]


def test_loop_marks_a_solo_tool_use_event_with_batch_size_one():
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[_tool_use_block("toolu_1", "calculator", {"expression": "2 + 2"})],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[_text_block("4")]),
        ]
    )
    events = []

    run_agent_loop(
        client, [{"role": "user", "content": "what is 2 + 2?"}], on_event=events.append
    )

    tool_use_events = [e for e in events if e["type"] == "tool_use"]
    assert tool_use_events == [
        {
            "type": "tool_use",
            "name": "calculator",
            "input": {"expression": "2 + 2"},
            "batch_index": 1,
            "batch_size": 1,
        }
    ]


def test_print_event_labels_a_batched_tool_use_but_not_a_solo_one(capsys):
    _print_event(
        {
            "type": "tool_use",
            "name": "web_search",
            "input": {"query": "France population"},
            "batch_index": 1,
            "batch_size": 2,
        }
    )
    _print_event(
        {
            "type": "tool_use",
            "name": "calculator",
            "input": {"expression": "2 + 2"},
            "batch_index": 1,
            "batch_size": 1,
        }
    )

    out = capsys.readouterr().out
    assert "tool_use (1 of 2 requested together):" in out
    assert 'web_search("France population")' in out
    assert 'tool_use:\ncalculator("2 + 2")' in out
    assert out.count("requested together") == 1


# Regression test for a /code-review finding: on_event previously emitted
# {"type": "end_turn"} for ANY non-tool_use stop_reason, including an anomalous one like
# "max_tokens", making a truncated response indistinguishable from normal completion to a
# caller driving off the event stream. Fix: a distinct "terminated" event carries the real
# stop_reason.

def test_loop_emits_terminated_event_for_a_non_end_turn_stop_reason(caplog):
    client = _ScriptedClient(
        [SimpleNamespace(stop_reason="max_tokens", content=[_text_block("cut off")])]
    )
    events = []

    with caplog.at_level(logging.WARNING):
        final_text, tool_calls, terminated_via = run_agent_loop(
            client, [{"role": "user", "content": "say a lot"}], on_event=events.append
        )

    assert final_text == "cut off"
    assert tool_calls == []
    assert terminated_via == "max_tokens"
    assert {"type": "terminated", "stop_reason": "max_tokens"} in events
    assert not any(e["type"] == "end_turn" for e in events)
    assert any("max_tokens" in record.message for record in caplog.records)


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
        final_text, tool_calls, terminated_via = run_agent_loop(
            client, [{"role": "user", "content": "loop forever"}], max_iterations=5
        )

    assert len(client.calls) == 5
    assert terminated_via == "max_iterations"
    assert any("MAX_ITERATIONS" in record.message for record in caplog.records)


# --- multi-step live acceptance test (design.md's live-API test strategy) -------------

@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="requires a live ANTHROPIC_API_KEY",
)
def test_multi_step_live_france_population_search_then_calculate():
    import anthropic

    client = anthropic.Anthropic()
    messages = [
        {
            "role": "user",
            "content": (
                "Find France's population using the web_search tool, then use the "
                "calculator tool to compute 10% of it. Report the final number."
            ),
        }
    ]

    final_text, tool_calls, terminated_via = run_agent_loop(client, messages)

    assert terminated_via == "end_turn"
    assert len(tool_calls) < MAX_ITERATIONS

    tool_names = [c["name"] for c in tool_calls]
    assert "web_search" in tool_names
    assert "calculator" in tool_names
    assert tool_names.index("web_search") < tool_names.index("calculator")

    calculator_call = next(c for c in tool_calls if c["name"] == "calculator")
    computed = tools.evaluate_expression(calculator_call["input"]["expression"])
    assert computed == pytest.approx(6_800_000, rel=0.01)

    assert final_text.strip()
