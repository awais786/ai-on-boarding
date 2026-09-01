"""The multi-tool agentic loop: drive Claude through tool_use round trips
until it signals end_turn, never inferring completion any other way.
"""

import logging

from . import tools

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_ITERATIONS = 20


def _extract_text(content_blocks):
    return "".join(block.text for block in content_blocks if block.type == "text")


def run_agent_loop(client, messages, max_iterations=MAX_ITERATIONS, on_event=None):
    """Drive a tool-use conversation with Claude until it signals end_turn.

    `messages` is the initial conversation (typically a single user message).
    Returns `(final_text, tool_calls, terminated_via)`:
    - `tool_calls` is the ordered list of `{"name": ..., "input": ...}` dicts
      for every tool Claude invoked along the way, so callers can verify what
      happened without parsing final text.
    - `terminated_via` is `"end_turn"` for normal completion, `"max_iterations"`
      if the safety cap was hit, or the raw `stop_reason` for any other
      terminal response - so callers can tell normal completion apart from the
      safety cap without guessing from the text.

    If given, `on_event(event)` is called for each step as it happens, where
    `event` is one of:
    - `{"type": "text", "text": ...}` - a text block Claude produced
    - `{"type": "tool_use", "name": ..., "input": ...}`
    - `{"type": "tool_result", "name": ..., "content": ..., "is_error": ...}`
    - `{"type": "end_turn"}` - normal completion
    - `{"type": "terminated", "stop_reason": ...}` - a terminal response with
      any `stop_reason` other than `tool_use` or `end_turn` (e.g. `max_tokens`)
    - `{"type": "max_iterations"}`
    This lets a caller render the running transcript without duplicating the
    loop's control flow.

    The cap is a safety guardrail, not the normal termination path: a request
    that stays within `max_iterations` always ends via `stop_reason ==
    "end_turn"` before the cap is reached.
    """
    emit = on_event if on_event is not None else lambda event: None
    messages = list(messages)
    tool_calls = []
    text = ""

    for _ in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=tools.TOOLS,
            messages=messages,
        )

        text = _extract_text(response.content)
        if text:
            emit({"type": "text", "text": text})

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tool_calls.append({"name": block.name, "input": block.input})
                emit({"type": "tool_use", "name": block.name, "input": block.input})
                outcome = tools.dispatch(block.name, block.input)
                is_error = "error" in outcome
                content_text = str(outcome["error"] if is_error else outcome["result"])
                emit(
                    {
                        "type": "tool_result",
                        "name": block.name,
                        "content": content_text,
                        "is_error": is_error,
                    }
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content_text,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
            continue

        if response.stop_reason == "end_turn":
            emit({"type": "end_turn"})
        else:
            logger.warning(
                "agent_loop: unexpected stop_reason %r, returning best-effort text",
                response.stop_reason,
            )
            emit({"type": "terminated", "stop_reason": response.stop_reason})
        return text, tool_calls, response.stop_reason

    logger.warning(
        "agent_loop: MAX_ITERATIONS (%d) reached without end_turn", max_iterations
    )
    emit({"type": "max_iterations"})
    return text, tool_calls, "max_iterations"
