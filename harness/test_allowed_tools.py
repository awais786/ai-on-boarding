"""Tests for the harness's allowed_tools enforcement.

Covers: an allowed tool executes; a disallowed tool is rejected and never
executed; the rejection identifies the denied tool; and the configured
allowlist -- not a hard-coded one -- is what's actually consulted.
"""
from __future__ import annotations

from harness.agent import create_agent
from harness.config import HarnessConfig
from harness.dispatcher import Dispatcher


def test_allowed_tool_executes(tmp_path):
    target = tmp_path / "hello.txt"
    target.write_text("hi")

    agent = create_agent()
    result = agent.call_tool("Read", path=str(target))

    assert result.ok is True
    assert result.output == "hi"


def test_disallowed_tool_is_rejected():
    agent = create_agent()

    result = agent.call_tool("WebFetch", url="https://example.com")

    assert result.ok is False


def test_disallowed_tool_is_never_executed(monkeypatch):
    executed = []

    def spy_webfetch(url: str) -> str:
        executed.append(url)
        return "should not run"

    config = HarnessConfig(allowed_tools=["Read"])
    dispatcher = Dispatcher(config, registry={"WebFetch": spy_webfetch})

    result = dispatcher.dispatch("WebFetch", url="https://example.com")

    assert result.ok is False
    assert executed == []


def test_denial_identifies_the_denied_tool():
    agent = create_agent()

    result = agent.call_tool("WebFetch", url="https://example.com")

    assert "WebFetch" in result.error
    assert "not permitted by the harness" in result.error


def test_configured_allowlist_is_used_not_hardcoded():
    """Bash is allowed by the shipped config.yaml, but a dispatcher built from a
    different HarnessConfig that omits it must deny Bash -- proving the
    allowlist actually consulted is the one passed in, not a list baked into
    the dispatcher.
    """
    restrictive_config = HarnessConfig(allowed_tools=["Read"])
    dispatcher = Dispatcher(restrictive_config)

    bash_result = dispatcher.dispatch("Bash", command="echo hi")
    read_result_denied = Dispatcher(HarnessConfig(allowed_tools=[])).dispatch(
        "Read", path=__file__
    )

    assert bash_result.ok is False
    assert "Bash" in bash_result.error
    assert read_result_denied.ok is False


def test_permissive_config_allows_bash():
    permissive_config = HarnessConfig(allowed_tools=["Bash"])
    dispatcher = Dispatcher(permissive_config)

    result = dispatcher.dispatch("Bash", command="printf ok")

    assert result.ok is True
    assert result.output == "ok"
