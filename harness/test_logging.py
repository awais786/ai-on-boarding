"""Tests for the dispatch logging devs rely on to see what the harness did."""
from __future__ import annotations

import logging

from harness.config import HarnessConfig
from harness.dispatcher import Dispatcher, _short


def test_denial_is_logged_as_a_warning_naming_the_tool(caplog):
    dispatcher = Dispatcher(HarnessConfig(allowed_tools=["Read"]))

    with caplog.at_level(logging.INFO, logger="harness"):
        dispatcher.dispatch("WebFetch", url="https://example.com")

    denials = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(denials) == 1
    assert "WebFetch" in denials[0].getMessage()
    assert "not in allowed_tools" in denials[0].getMessage()


def test_allowed_call_logs_the_run_and_the_outcome(caplog, tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi")
    dispatcher = Dispatcher(HarnessConfig(allowed_tools=["Read"]))

    with caplog.at_level(logging.INFO, logger="harness"):
        dispatcher.dispatch("Read", path=str(target))

    messages = [r.getMessage() for r in caplog.records]
    assert any("allowed Read(" in m for m in messages)
    assert any("Read succeeded" in m for m in messages)


def test_tool_failure_is_logged(caplog):
    dispatcher = Dispatcher(HarnessConfig(allowed_tools=["Bash"]))

    with caplog.at_level(logging.INFO, logger="harness"):
        dispatcher.dispatch("Bash", command="exit 3")

    failures = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(failures) == 1
    assert "Bash failed" in failures[0].getMessage()


def test_nothing_is_logged_above_debug_when_quiet(caplog):
    """Importers who never opt in shouldn't get harness output in their logs."""
    dispatcher = Dispatcher(HarnessConfig(allowed_tools=["Read"]))

    with caplog.at_level(logging.CRITICAL, logger="harness"):
        dispatcher.dispatch("Read", path=__file__)

    assert caplog.records == []


def test_long_values_are_truncated_in_log_lines():
    rendered = _short("x" * 5000)

    assert len(rendered) < 200
    assert "5002 chars" in rendered
