"""Tests for the multi-tool agent loop, derived from
openspec/changes/42-multi-tool-claude-agent-loop/specs/multi-tool-agent-loop/spec.md.

Requirement -> what a test needs to assert (task 4.1, revised for the PR #43 review change that
replaced the client-side web_search stub with Anthropic's provider-executed server tool):
- Register a calculator tool: TOOLS declares name/description/input_schema requiring
  `expression` (string); evaluates arithmetic; returns an error result (not a raised
  exception) for non-arithmetic input or division by zero.
- Register a web-search tool: TOOLS declares the `web_search_20260209` server tool
  (type/name/max_uses/allowed_callers) - no input_schema, no client handler, no dispatch()
  branch.
- Surface server-executed web-search activity without dispatching it: a `server_tool_use`
  block naming web_search and its `web_search_tool_result` block are surfaced via on_event,
  never passed to agent_loop.dispatch and never fed back as a client-constructed tool_result.
- Execute a requested tool and return its result: on stop_reason == "tool_use", the loop
  executes the named client tool (calculator), appends Claude's assistant message and a user
  message with the tool_result to the conversation, and sends it back.
- Terminate only on end_turn: the loop must not stop on a text content block accompanying
  a tool_use response; it must stop only when stop_reason == "end_turn".
- Support multiple sequential tool calls: a server-executed web_search (no client round trip)
  followed by a client calculator round trip before end_turn.
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

import agent_loop
from agent_loop import MAX_ITERATIONS, _print_event, run_agent_loop


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(block_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=tool_input)


def _server_tool_use_block(block_id, name, tool_input):
    return SimpleNamespace(type="server_tool_use", id=block_id, name=name, input=tool_input)


def _web_search_tool_result_block(tool_use_id, results):
    content = [SimpleNamespace(title=r["title"], url=r["url"]) for r in results]
    return SimpleNamespace(type="web_search_tool_result", tool_use_id=tool_use_id, content=content)


def _web_search_tool_result_error_block(tool_use_id, error_code):
    content = SimpleNamespace(error_code=error_code)
    return SimpleNamespace(type="web_search_tool_result", tool_use_id=tool_use_id, content=content)


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
    schema = next(t for t in agent_loop.TOOLS if t["name"] == "calculator")
    assert schema["name"] == "calculator"
    assert schema["description"]
    assert schema["input_schema"]["required"] == ["expression"]
    assert schema["input_schema"]["properties"]["expression"]["type"] == "string"


def test_calculator_evaluates_arithmetic_expression():
    assert agent_loop.dispatch("calculator", {"expression": "68000000 * 0.10"}) == {
        "result": 6800000.0
    }


def test_calculator_rejects_non_arithmetic_expression_without_raising():
    outcome = agent_loop.dispatch(
        "calculator", {"expression": "__import__('os').system('echo hi')"}
    )
    assert "error" in outcome


def test_calculator_reports_division_by_zero_as_error_not_exception():
    assert agent_loop.dispatch("calculator", {"expression": "1 / 0"}) == {
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
    outcome = agent_loop.dispatch(
        "calculator", {"expression": "1" + "0" * 400 + " * 1.5"}
    )
    assert outcome == {"error": "expression too long (max 200 characters)"}


def test_calculator_rejects_expression_over_the_length_cap_before_it_can_recurse():
    outcome = agent_loop.dispatch("calculator", {"expression": "+".join(["1"] * 5000)})
    assert outcome == {"error": "expression too long (max 200 characters)"}


# Regression test for a /code-review finding: a short expression under the length cap can
# still overflow float range via Python's own literal parsing (ast.parse() folds an
# out-of-range scientific-notation literal to inf before evaluate_expression() ever sees
# it), which the length cap and the ArithmeticError handler both miss since no exception is
# raised. Fix: evaluate_expression() rejects a non-finite result after evaluation.

def test_calculator_rejects_expression_that_evaluates_to_a_non_finite_result():
    outcome = agent_loop.dispatch("calculator", {"expression": "1e400"})
    assert "error" in outcome


# --- web_search tool: Anthropic's provider-executed server tool ---------------------
# Regression tests for the PR #43 review request: web_search is no longer a client-side
# stub. It is declared as a server tool the API executes directly - there is no schema,
# handler, or dispatch() branch for it in this code.

def test_web_search_is_declared_as_a_provider_executed_server_tool():
    schema = next(t for t in agent_loop.TOOLS if t["name"] == "web_search")
    assert schema == {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 3,
        "allowed_callers": ["direct"],
    }


def test_web_search_has_no_client_side_dispatch_handler():
    assert "web_search" not in agent_loop._TOOL_FUNCTIONS


def test_dispatch_reports_web_search_as_unknown_since_it_has_no_client_handler():
    outcome = agent_loop.dispatch("web_search", {"query": "France population"})
    assert outcome == {"error": "unknown tool: web_search"}


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
    ],
)
def test_dispatch_returns_error_result_for_malformed_input_instead_of_raising(
    name, tool_input
):
    outcome = agent_loop.dispatch(name, tool_input)
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
    # The server-executed web_search costs no client round trip - its server_tool_use/
    # web_search_tool_result blocks arrive in the same response as the calculator tool_use
    # block, so only calculator shows up as a client round trip and in `tool_calls`.
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    _server_tool_use_block(
                        "srvtoolu_1", "web_search", {"query": "France population"}
                    ),
                    _web_search_tool_result_block(
                        "srvtoolu_1",
                        [{"title": "France - Population", "url": "https://example.com/france"}],
                    ),
                    _tool_use_block(
                        "toolu_2", "calculator", {"expression": "68000000 * 0.10"}
                    ),
                ],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[_text_block("6.8 million")]),
        ]
    )

    final_text, tool_calls, terminated_via = run_agent_loop(
        client, [{"role": "user", "content": "Find France population and calculate 10%."}]
    )

    assert [c["name"] for c in tool_calls] == ["calculator"]
    assert final_text == "6.8 million"
    assert terminated_via == "end_turn"
    assert len(client.calls) == 2


# --- loop: server-executed web_search is surfaced but never dispatched --------------

def test_loop_surfaces_server_tool_use_and_web_search_result_without_dispatching():
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="end_turn",
                content=[
                    _server_tool_use_block(
                        "srvtoolu_1", "web_search", {"query": "France population"}
                    ),
                    _web_search_tool_result_block(
                        "srvtoolu_1",
                        [{"title": "France - Population", "url": "https://example.com/france"}],
                    ),
                    _text_block("France's population is about 68 million."),
                ],
            ),
        ]
    )
    events = []

    final_text, tool_calls, terminated_via = run_agent_loop(
        client, [{"role": "user", "content": "What is France's population?"}],
        on_event=events.append,
    )

    assert tool_calls == []
    assert terminated_via == "end_turn"
    assert len(client.calls) == 1

    event_types = [e["type"] for e in events]
    assert "server_tool_use" in event_types
    assert "web_search_result" in event_types
    assert "tool_use" not in event_types
    assert "tool_result" not in event_types

    server_tool_use_event = next(e for e in events if e["type"] == "server_tool_use")
    assert server_tool_use_event["name"] == "web_search"
    assert server_tool_use_event["input"] == {"query": "France population"}

    web_search_result_event = next(e for e in events if e["type"] == "web_search_result")
    assert web_search_result_event["is_error"] is False
    assert web_search_result_event["content"] == [
        {"title": "France - Population", "url": "https://example.com/france"}
    ]


def test_loop_surfaces_a_web_search_error_result():
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="end_turn",
                content=[
                    _server_tool_use_block("srvtoolu_1", "web_search", {"query": "anything"}),
                    _web_search_tool_result_error_block("srvtoolu_1", "unavailable"),
                    _text_block("I couldn't search right now."),
                ],
            ),
        ]
    )
    events = []

    run_agent_loop(
        client, [{"role": "user", "content": "search for anything"}], on_event=events.append
    )

    web_search_result_event = next(e for e in events if e["type"] == "web_search_result")
    assert web_search_result_event["is_error"] is True
    assert web_search_result_event["content"] == {"error_code": "unavailable"}


# --- loop: multiple tool_use blocks in one turn are labeled as requested together -----

def test_loop_annotates_tool_use_events_with_batch_position_when_requested_together():
    # "translate" is a fictitious client tool used only to exercise generic batch-labeling
    # mechanics with two distinct tool_use blocks - web_search is never a valid choice here,
    # since it is server-executed and never produces a tool_use block.
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    _tool_use_block("toolu_1", "translate", {"text": "bonjour"}),
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
    # "translate" is fictitious, same rationale as above - a client tool_use block never
    # names web_search.
    _print_event(
        {
            "type": "tool_use",
            "name": "translate",
            "input": {"text": "bonjour"},
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
    assert 'translate("bonjour")' in out
    assert 'tool_use:\ncalculator("2 + 2")' in out
    assert out.count("requested together") == 1


def test_print_event_renders_server_tool_use_and_web_search_result(capsys):
    _print_event(
        {"type": "server_tool_use", "name": "web_search", "input": {"query": "France population"}}
    )
    _print_event(
        {
            "type": "web_search_result",
            "is_error": False,
            "content": [{"title": "France - Population", "url": "https://example.com/france"}],
        }
    )
    _print_event({"type": "web_search_result", "is_error": True, "content": {"error_code": "unavailable"}})

    out = capsys.readouterr().out
    assert "server_tool_use" in out
    assert 'web_search("France population")' in out
    assert "web_search_result:" in out
    assert "France - Population" in out
    assert "web_search_result (error):" in out
    assert "unavailable" in out


def test_print_event_renders_pause_turn(capsys):
    _print_event({"type": "pause_turn"})

    out = capsys.readouterr().out
    assert "server paused" in out


# Regression test for a /code-review finding: a "pause_turn" stop_reason (the server pausing a
# long-running turn - e.g. several server-executed web_search calls in one turn) was falling
# into the generic "any other stop_reason is terminal" branch, ending the loop and truncating
# the answer instead of resending the paused response so the server could continue, per
# Anthropic's own tool-runner handling of this stop_reason.

def test_loop_resends_on_pause_turn_instead_of_terminating():
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="pause_turn",
                content=[_server_tool_use_block("srvtoolu_1", "web_search", {"query": "a"})],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[_text_block("done")]),
        ]
    )
    events = []

    final_text, tool_calls, terminated_via = run_agent_loop(
        client, [{"role": "user", "content": "search for a lot of things"}],
        on_event=events.append,
    )

    assert len(client.calls) == 2
    assert terminated_via == "end_turn"
    assert final_text == "done"
    assert {"type": "pause_turn"} in events
    assert not any(e["type"] == "terminated" for e in events)

    second_call_messages = client.calls[1]["messages"]
    assert second_call_messages[-1]["role"] == "assistant"


# Regression test for a /code-review finding: a response with stop_reason == "pause_turn" that
# also carries a client tool_use block would silently drop that tool_use block - never
# dispatched, no tool_result ever produced for it - since the old pause_turn branch only
# appended the assistant message and resent, never scanning for tool_use blocks the way the
# tool_use branch did. Fix: pause_turn and tool_use are handled by the same branch, which always
# dispatches any tool_use blocks present regardless of which of the two stop_reasons triggered it.

def test_loop_dispatches_tool_use_blocks_present_alongside_pause_turn():
    client = _ScriptedClient(
        [
            SimpleNamespace(
                stop_reason="pause_turn",
                content=[
                    _server_tool_use_block("srvtoolu_1", "web_search", {"query": "a"}),
                    _tool_use_block("toolu_1", "calculator", {"expression": "2 + 2"}),
                ],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[_text_block("done")]),
        ]
    )
    events = []

    final_text, tool_calls, terminated_via = run_agent_loop(
        client, [{"role": "user", "content": "search and calculate"}], on_event=events.append
    )

    assert terminated_via == "end_turn"
    assert tool_calls == [{"name": "calculator", "input": {"expression": "2 + 2"}}]
    assert {"type": "pause_turn"} in events

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
    events = []

    final_text, tool_calls, terminated_via = run_agent_loop(
        client, messages, on_event=events.append
    )

    assert terminated_via == "end_turn"
    assert len(tool_calls) < MAX_ITERATIONS

    # web_search is now server-executed: it never appears in tool_calls (which tracks only
    # client tool_use blocks), only as a server_tool_use/web_search_result event pair.
    server_tool_use_events = [e for e in events if e["type"] == "server_tool_use"]
    assert any(e["name"] == "web_search" for e in server_tool_use_events)
    assert any(e["type"] == "web_search_result" for e in events)

    # Tolerant of the model calling calculator more than once (non-determinism, per
    # design.md's Risks note) - the structural invariant that matters is that web_search
    # never shows up here at all, since it's server-executed and never a tool_use block.
    tool_names = [c["name"] for c in tool_calls]
    assert "calculator" in tool_names
    assert all(name == "calculator" for name in tool_names)

    calculator_tool_use_events = [
        e for e in events if e["type"] == "tool_use" and e["name"] == "calculator"
    ]
    first_search_index = events.index(server_tool_use_events[0])
    first_calculator_index = events.index(calculator_tool_use_events[0])
    assert first_search_index < first_calculator_index

    # Check every calculator call, not just the first, since a non-deterministic model may
    # make an earlier unrelated calculator call (e.g. a sanity check) before the real
    # population-percentage one - asserting only on tool_calls[0] would make this test fail
    # on a call that has nothing to do with the assertion below, contradicting the tolerance
    # for repeat calculator calls established just above.
    computed_values = [
        agent_loop.evaluate_expression(c["input"]["expression"])
        for c in tool_calls
        if c["name"] == "calculator"
    ]
    # France's real population is roughly 65-69 million - a generous band rather than
    # pinning to the old fixed stub value, since the figure now comes from a real search.
    assert any(5_500_000 < computed < 7_500_000 for computed in computed_values)

    assert final_text.strip()
