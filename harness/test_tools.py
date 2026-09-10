"""Tests for tool behaviour itself, separate from the allowlist policy."""
from __future__ import annotations

import pytest

from harness.config import HarnessConfig
from harness.dispatcher import Dispatcher
from harness.tools import tool_bash


def test_bash_nonzero_exit_is_reported_as_failure():
    dispatcher = Dispatcher(HarnessConfig(allowed_tools=["Bash"]))

    result = dispatcher.dispatch("Bash", command="exit 3")

    assert result.ok is False
    assert "exited 3" in result.error


def test_bash_nonzero_exit_keeps_the_output_in_the_error():
    dispatcher = Dispatcher(HarnessConfig(allowed_tools=["Bash"]))

    result = dispatcher.dispatch("Bash", command="echo boom >&2; exit 1")

    assert result.ok is False
    assert "boom" in result.error


def test_bash_success_returns_output():
    dispatcher = Dispatcher(HarnessConfig(allowed_tools=["Bash"]))

    result = dispatcher.dispatch("Bash", command="printf ok")

    assert result.ok is True
    assert result.output == "ok"


def test_tool_bash_raises_directly_on_failure():
    with pytest.raises(RuntimeError, match="exited 3"):
        tool_bash("exit 3")
