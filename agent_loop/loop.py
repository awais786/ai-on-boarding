"""The agent loop: ask, execute what the model asks for, feed the result back, ask again.

The loop ends when the model says it has ended, and at no other time. It does not
read the shape of the response, or its wording, or count turns to decide it is
finished - those all describe a response that *looks* complete, which is not the
same thing as one the model reported as complete.

Every value of the stop reason is accounted for. The two the loop can act on are
handled; anything else stops the run and says what it was, because a response the
loop cannot act on is not an answer and must not be returned as one.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from agent_loop.tools import TOOLS, ToolResult, dispatch

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 20
"""A safeguard against a run that cannot finish - never how a normal run ends."""

DEFAULT_MODEL = "claude-haiku-4-5"
MODEL_VARIABLE = "AGENT_LOOP_MODEL"
MAX_TOKENS = 2048

REQUESTING_A_TOOL = "tool_use"
FINISHED = "end_turn"


class AgentLoopError(Exception):
    """The run did not produce an answer."""


class IterationLimitExceeded(AgentLoopError):
    """The safety cap was reached before the model reported it had finished."""


class UnusableResponse(AgentLoopError):
    """The model returned a response the loop cannot act on."""


@dataclass(frozen=True)
class Event:
    """Something the loop did, for a caller that wants to watch it happen."""

    iteration: int
    stop_reason: str | None = None
    tool_name: str | None = None
    tool_input: Mapping[str, Any] | None = None
    result: ToolResult | None = None


class _Client(Protocol):
    """The part of the model client this loop uses."""

    @property
    def messages(self) -> Any: ...


def _default_client() -> _Client:
    # Imported and constructed only when no client was supplied, so that a caller
    # passing its own client never needs a credential.
    import anthropic

    return anthropic.Anthropic()


def resolve_model(model: str | None = None) -> str:
    """The model to use: the one asked for, else the environment's, else the default."""
    return model or os.environ.get(MODEL_VARIABLE) or DEFAULT_MODEL


def _text_of(content: list[Any]) -> str:
    return "\n".join(block.text for block in content if block.type == "text").strip()


def run(
    prompt: str,
    *,
    client: _Client | None = None,
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_iterations: int = MAX_ITERATIONS,
    on_event: Callable[[Event], None] | None = None,
) -> str:
    """Run the loop until the model reports it has finished, and return its answer.

    Raises `UnusableResponse` if the model returns something the loop cannot act on,
    and `IterationLimitExceeded` if the safety cap is reached first. Neither is
    returned as an answer: a caller cannot mistake a run that gave up for one that
    finished.
    """
    client = client or _default_client()
    model = resolve_model(model)
    tools = TOOLS if tools is None else tools
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    def emit(event: Event) -> None:
        if on_event is not None:
            on_event(event)

    for iteration in range(1, max_iterations + 1):
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            tools=tools,
            messages=messages,
        )
        stop_reason = response.stop_reason
        logger.info("iteration %d: stop_reason=%s", iteration, stop_reason)
        emit(Event(iteration=iteration, stop_reason=stop_reason))

        if stop_reason == FINISHED:
            return _text_of(response.content)

        if stop_reason != REQUESTING_A_TOOL:
            logger.error("iteration %d: unusable stop reason %r", iteration, stop_reason)
            raise UnusableResponse(
                f"the model stopped with {stop_reason!r}, which this loop cannot act on"
            )

        requests = [block for block in response.content if block.type == REQUESTING_A_TOOL]
        if not requests:
            # Answering this with an empty turn is rejected outright, and would report a
            # failure from the far end of the wire that says nothing about the cause.
            logger.error("iteration %d: a tool was requested but none was named", iteration)
            raise UnusableResponse(
                "the model reported it was requesting a tool but named none"
            )

        # The response goes back whole. Rebuilding it from the parts the loop recognises
        # would discard any reasoning the model produced alongside its request, which must
        # be returned unchanged, and would break the pairing of request to result.
        messages.append({"role": "assistant", "content": response.content})

        results = []
        for request in requests:
            result = dispatch(request.name, request.input)
            logger.info("iteration %d: %s -> %s", iteration, request.name, result.content)
            emit(
                Event(
                    iteration=iteration,
                    tool_name=request.name,
                    tool_input=request.input,
                    result=result,
                )
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": request.id,
                    "content": result.content,
                    "is_error": result.is_error,
                }
            )

        # Every result for this response goes back in one turn, never spread across several.
        messages.append({"role": "user", "content": results})

    logger.warning(
        "reached the safety cap of %d iterations without the model reporting it had finished",
        max_iterations,
    )
    raise IterationLimitExceeded(
        f"stopped after {max_iterations} iterations without the model finishing its turn"
    )
