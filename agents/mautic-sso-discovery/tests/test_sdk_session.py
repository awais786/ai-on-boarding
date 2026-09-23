from __future__ import annotations

import functools

import anyio
import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from mautic_sso_discovery.sdk_session import collect_final_text


def _result(**overrides) -> ResultMessage:
    defaults = dict(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="test-session",
        terminal_reason="completed",
    )
    return ResultMessage(**{**defaults, **overrides})


def _run(query_impl) -> str:
    return anyio.run(functools.partial(collect_final_text, "prompt", None, query_impl=query_impl))


def test_collect_final_text_returns_last_nonempty_assistant_text():
    async def query_impl(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text="exploring...")], model="test")
        yield AssistantMessage(content=[TextBlock(text="final answer")], model="test")
        yield _result()

    assert _run(query_impl) == "final answer"


def test_collect_final_text_raises_without_a_result_message():
    async def query_impl(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text="final answer")], model="test")

    with pytest.raises(RuntimeError, match="ResultMessage"):
        _run(query_impl)


def test_collect_final_text_raises_on_is_error():
    async def query_impl(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text="final answer")], model="test")
        yield _result(is_error=True, subtype="error_during_execution")

    with pytest.raises(RuntimeError, match="error"):
        _run(query_impl)


def test_collect_final_text_raises_on_max_turns_truncation():
    async def query_impl(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text="still going...")], model="test")
        yield _result(terminal_reason="max_turns")

    with pytest.raises(RuntimeError, match="max_turns"):
        _run(query_impl)


def test_collect_final_text_accepts_none_terminal_reason():
    """None is documented as normal on older CLI versions or a result that
    bypassed the query loop - must not be treated as a failure.
    """

    async def query_impl(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text="final answer")], model="test")
        yield _result(terminal_reason=None)

    assert _run(query_impl) == "final answer"
