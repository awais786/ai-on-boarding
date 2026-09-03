"""The command-line entry point: it must show the lifecycle, and fail cleanly."""

from __future__ import annotations

import agent_loop.__main__ as cli
from agent_loop.loop import Event, UnusableResponse
from agent_loop.tools import ToolResult


def test_a_response_event_prints_its_stop_reason(capsys):
    cli._show(Event(iteration=2, stop_reason="tool_use"))
    assert "iter 2  stop_reason=tool_use" in capsys.readouterr().out


def test_an_event_with_no_stop_reason_at_all_is_still_shown(capsys):
    """The loop reports a stop reason before judging it, so `None` reaches the printer."""
    cli._show(Event(iteration=1, stop_reason=None))
    assert "iter 1  stop_reason=None" in capsys.readouterr().out


def test_a_tool_event_prints_the_call_and_its_result(capsys):
    cli._show(
        Event(
            iteration=1,
            tool_name="calculator",
            tool_input={"expression": "6 * 7"},
            result=ToolResult("42"),
        )
    )
    printed = capsys.readouterr().out
    assert "calculator(expression='6 * 7')" in printed
    assert "42" in printed


def test_a_failed_tool_call_is_marked_in_the_transcript(capsys):
    cli._show(Event(iteration=1, tool_name="calculator", tool_input={}, result=ToolResult("e", True)))
    assert "->!" in capsys.readouterr().out


def test_a_run_that_produces_no_answer_reports_it_rather_than_raising(monkeypatch, capsys):
    def refuse(*args, **kwargs):
        raise UnusableResponse("the model stopped with 'max_tokens'")

    monkeypatch.setattr(cli, "run", refuse)

    assert cli.main(["anything"]) == 1
    assert "no answer" in capsys.readouterr().err


def test_a_successful_run_prints_the_answer(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run", lambda *a, **k: "14180")

    assert cli.main(["anything"]) == 0
    assert "answer: 14180" in capsys.readouterr().out
