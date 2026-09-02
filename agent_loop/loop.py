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


def _summarize_web_search_result_content(content, is_error):
    if is_error:
        return {"error_code": getattr(content, "error_code", "unknown_error")}
    return [
        {"title": getattr(item, "title", None), "url": getattr(item, "url", None)}
        for item in content
    ]


def _emit_server_tool_events(content_blocks, emit):
    """Surface Anthropic's provider-executed tool activity (currently just web_search).

    These blocks are informational only: the server already executed the search and
    returned its result within this same response, so nothing here is dispatched or
    fed back as a client-constructed tool_result.
    """
    for block in content_blocks:
        if block.type == "server_tool_use":
            emit({"type": "server_tool_use", "name": block.name, "input": block.input})
        elif block.type == "web_search_tool_result":
            is_error = not isinstance(block.content, list)
            emit(
                {
                    "type": "web_search_result",
                    "is_error": is_error,
                    "content": _summarize_web_search_result_content(block.content, is_error),
                }
            )


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
    - `{"type": "tool_use", "name": ..., "input": ..., "batch_index": ..., "batch_size": ...}` -
      `batch_index` (1-based) and `batch_size` are this tool call's position and the total
      number of `tool_use` blocks in the response it came from; `batch_size == 1` means it
      arrived alone
    - `{"type": "tool_result", "name": ..., "content": ..., "is_error": ...}`
    - `{"type": "server_tool_use", "name": ..., "input": ...}` - Anthropic's servers invoked a
      provider-executed tool (currently just `web_search`); informational only - this is never
      dispatched or fed back as a client tool_result, since the server already executed it
    - `{"type": "web_search_result", "content": ..., "is_error": ...}` - the result of that
      server-executed search, paired with the `server_tool_use` event above
    - `{"type": "pause_turn"}` - the server paused a long-running turn and expects the response
      resent unchanged to continue; not terminal, the loop resends and keeps going
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

        _emit_server_tool_events(response.content, emit)

        text = _extract_text(response.content)
        if text:
            emit({"type": "text", "text": text})

        if response.stop_reason in ("tool_use", "pause_turn"):
            # "pause_turn" (the server paused a long-running turn - e.g. several
            # server-executed web_search calls in one turn) is handled alongside "tool_use"
            # rather than as a separate terminal-looking branch, since a paused response can
            # in principle still carry a client tool_use block needing dispatch. Either way,
            # the assistant content is appended once and the loop resends/continues - per
            # Anthropic's own tool-runner handling of "pause_turn", this is not terminal.
            messages.append({"role": "assistant", "content": response.content})
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            if tool_use_blocks:
                batch_size = len(tool_use_blocks)
                tool_results = []
                for batch_index, block in enumerate(tool_use_blocks, start=1):
                    tool_calls.append({"name": block.name, "input": block.input})
                    emit(
                        {
                            "type": "tool_use",
                            "name": block.name,
                            "input": block.input,
                            "batch_index": batch_index,
                            "batch_size": batch_size,
                        }
                    )
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
            if response.stop_reason == "pause_turn":
                emit({"type": "pause_turn"})
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
