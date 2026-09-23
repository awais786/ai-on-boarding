"""Shared by both Agent SDK sessions (discover, propose-issues): runs one
one-shot `query()` call and returns the final assistant text - but only if
the session actually finished cleanly. Without this check, a session that
hit max_turns, was aborted, or errored mid-stream still leaves whatever
partial text the model last wrote, which would otherwise get treated as a
finished report (and, in propose-issues, could get partial issues created
for real from a truncated draft).
"""
from __future__ import annotations

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock

# terminal_reason values that mean the query loop didn't reach a normal,
# complete stop - see ResultMessage.terminal_reason's docstring in the
# installed SDK. None is accepted: the SDK reports it as normal on older
# CLI versions or a result that bypassed the query loop entirely.
_INCOMPLETE_TERMINAL_REASONS = {"max_turns", "aborted_streaming", "aborted_tools"}


async def collect_final_text(prompt: str, options: ClaudeAgentOptions, *, query_impl) -> str:
    last_text = ""
    result: ResultMessage | None = None

    async for message in query_impl(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            text = "".join(block.text for block in message.content if isinstance(block, TextBlock))
            if text:
                last_text = text
        elif isinstance(message, ResultMessage):
            result = message

    if result is None:
        raise RuntimeError("session ended without a ResultMessage - cannot confirm it completed successfully")
    if result.is_error:
        raise RuntimeError(f"session reported an error (subtype={result.subtype!r}, terminal_reason={result.terminal_reason!r})")
    if result.terminal_reason in _INCOMPLETE_TERMINAL_REASONS:
        raise RuntimeError(f"session did not complete normally (terminal_reason={result.terminal_reason!r}) - the report is likely truncated")

    return last_text
