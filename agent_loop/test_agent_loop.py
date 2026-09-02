"""Tests for the multi-tool Claude agent loop, written from
openspec/specs/multi-tool-agent-loop/spec.md.

Requirement -> assertion map (task 4.1):
- Tool Definitions -> test_tool_definitions_have_valid_json_schema
- Stop-Reason-Driven Loop Termination -> test_lifecycle_web_search_then_calculator_then_end_turn,
  test_end_turn_termination_does_not_depend_on_content_order
- Tool Use Extraction and Execution -> test_lifecycle_web_search_then_calculator_then_end_turn,
  test_multiple_tool_use_blocks_in_one_response_are_all_executed
- Tool Dispatcher and Unknown Tool Handling -> test_dispatch_tool_routes_calculator,
  test_dispatch_tool_routes_web_search, test_dispatch_tool_unknown_name_is_not_silently_ignored
- Multi-Step Sequential Tool Calls -> test_lifecycle_web_search_then_calculator_then_end_turn
- Safety Iteration Cap -> test_lifecycle_web_search_then_calculator_then_end_turn (finishes well
  under the cap), test_max_iterations_reached_stops_and_logs_warning
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

from agent_loop.loop import MAX_ITERATIONS, run_agent_loop
from agent_loop.tools import TOOLS, dispatch_tool, web_search


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(block_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=tool_input)


def response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def scripted_client(responses):
    """A MagicMock client whose messages.create returns `responses` in order and records a
    shallow snapshot of the `messages` kwarg at call time (the loop mutates and reuses the same
    list object across iterations, so call_args_list would otherwise all reflect the final state).
    """
    remaining = list(responses)
    snapshots = []

    def side_effect(*args, **kwargs):
        snapshots.append(list(kwargs["messages"]))
        return remaining.pop(0)

    client = MagicMock()
    client.messages.create.side_effect = side_effect
    return client, snapshots


def test_tool_definitions_have_valid_json_schema():
    assert {tool["name"] for tool in TOOLS} == {"calculator", "web_search"}
    for tool in TOOLS:
        assert tool["name"]
        assert tool["description"]
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert schema["required"] == list(schema["properties"].keys())

    calculator_schema = next(t for t in TOOLS if t["name"] == "calculator")["input_schema"]
    assert calculator_schema["properties"]["expression"]["type"] == "string"
    assert "expression" in calculator_schema["required"]

    web_search_schema = next(t for t in TOOLS if t["name"] == "web_search")["input_schema"]
    assert web_search_schema["properties"]["query"]["type"] == "string"
    assert "query" in web_search_schema["required"]


def test_dispatch_tool_routes_calculator():
    result_text, is_error = dispatch_tool("calculator", {"expression": "2 + 2"})
    assert result_text == "4"
    assert is_error is False


def test_dispatch_tool_routes_web_search():
    result_text, is_error = dispatch_tool("web_search", {"query": "France population"})
    assert result_text == "France population is 68 million."
    assert is_error is False


def test_dispatch_tool_malformed_input_does_not_crash_the_loop():
    """A recognized tool with input missing its required field must return an is_error
    tool_result, not raise — the input_schema is a hint to the model, not an API-enforced
    guarantee. Covers both calculator and web_search symmetrically."""
    calc_text, calc_is_error = dispatch_tool("calculator", {})
    assert calc_is_error is True
    assert calc_text

    search_text, search_is_error = dispatch_tool("web_search", {})
    assert search_is_error is True
    assert search_text


def test_dispatch_tool_unknown_name_is_not_silently_ignored():
    result_text, is_error = dispatch_tool("time_machine", {"year": 1999})
    assert is_error is True
    assert "time_machine" in result_text
    assert "unrecognized" in result_text.lower()


def test_lifecycle_web_search_then_calculator_then_end_turn():
    """The full web_search -> calculator -> end_turn lifecycle for the worked example prompt."""
    search_result_text = web_search("France population")
    calculator_result_text, _ = dispatch_tool("calculator", {"expression": "68000000 * 0.10"})

    responses = [
        response(
            content=[
                text_block("I'll search for it."),
                tool_use_block("toolu_01", "web_search", {"query": "France population"}),
            ],
            stop_reason="tool_use",
        ),
        response(
            content=[
                text_block("Now I'll calculate 10%."),
                tool_use_block(
                    "toolu_02", "calculator", {"expression": "68000000 * 0.10"}
                ),
            ],
            stop_reason="tool_use",
        ),
        response(
            content=[text_block(f"10% is {calculator_result_text}.")],
            stop_reason="end_turn",
        ),
    ]

    client, snapshots = scripted_client(responses)

    result = run_agent_loop("Find France population and calculate 10%.", client=client)

    # Claude requested web_search, then calculator, then finished normally.
    assert client.messages.create.call_count == 3
    assert client.messages.create.call_count < MAX_ITERATIONS

    assert snapshots[0] == [
        {"role": "user", "content": "Find France population and calculate 10%."}
    ]

    # After the web_search tool_use, its result was appended with the matching tool_use_id.
    assert snapshots[1][-2] == {"role": "assistant", "content": responses[0].content}
    web_search_tool_result = snapshots[1][-1]["content"][0]
    assert web_search_tool_result["tool_use_id"] == "toolu_01"
    assert web_search_tool_result["content"] == search_result_text
    assert "68" in search_result_text  # the fact the calculator input below is derived from

    # Claude's calculator call used the value obtained from the web_search result.
    calculator_call_input = responses[1].content[1].input
    assert "68000000" in calculator_call_input["expression"]

    # The calculator tool_result was appended with the matching tool_use_id.
    assert snapshots[2][-2] == {"role": "assistant", "content": responses[1].content}
    calculator_tool_result = snapshots[2][-1]["content"][0]
    assert calculator_tool_result["tool_use_id"] == "toolu_02"
    assert calculator_tool_result["content"] == calculator_result_text

    # The loop terminated via stop_reason == "end_turn" and returned the final text,
    # which contains the calculated result.
    assert calculator_result_text in result


def test_multiple_tool_use_blocks_in_one_response_are_all_executed():
    responses = [
        response(
            content=[
                tool_use_block("toolu_a", "calculator", {"expression": "1 + 1"}),
                tool_use_block("toolu_b", "web_search", {"query": "unmapped query"}),
            ],
            stop_reason="tool_use",
        ),
        response(content=[text_block("done")], stop_reason="end_turn"),
    ]
    client, snapshots = scripted_client(responses)

    result = run_agent_loop("do two things", client=client)

    assert result == "done"
    tool_results = snapshots[1][-1]["content"]
    assert len(tool_results) == 2
    assert {r["tool_use_id"] for r in tool_results} == {"toolu_a", "toolu_b"}
    calc_result = next(r for r in tool_results if r["tool_use_id"] == "toolu_a")
    assert calc_result["content"] == "2"


def test_end_turn_termination_does_not_depend_on_content_order():
    """Termination must be driven by stop_reason alone, not response.content[0].type."""
    weird_first_block = SimpleNamespace(type="thinking")  # deliberately no .text attribute
    responses = [
        response(
            content=[weird_first_block, text_block("the real answer")],
            stop_reason="end_turn",
        )
    ]
    client = MagicMock()
    client.messages.create.side_effect = responses

    result = run_agent_loop("anything", client=client)

    assert result == "the real answer"


def test_max_iterations_reached_stops_and_logs_warning(caplog):
    always_tool_use = response(
        content=[tool_use_block("toolu_x", "calculator", {"expression": "1 + 1"})],
        stop_reason="tool_use",
    )
    client = MagicMock()
    client.messages.create.return_value = always_tool_use

    with caplog.at_level(logging.WARNING, logger="agent_loop.loop"):
        result = run_agent_loop("never finishes", client=client)

    assert client.messages.create.call_count == MAX_ITERATIONS
    assert result == ""
    assert any("MAX_ITERATIONS" in record.message for record in caplog.records)
