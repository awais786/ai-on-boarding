"""Run the agent loop by hand and watch it work.

    python -m agent_loop "What is the population of Tokyo divided by 1000?"

Prints one line per iteration with the stop reason that drove the decision, and a
line for each tool call and its result, so the lifecycle is visible rather than
inferred from the final answer.
"""

from __future__ import annotations

import argparse
import sys

from agent_loop.loop import AgentLoopError, Event, resolve_model, run

DEFAULT_PROMPT = "What is the population of Tokyo divided by 1000?"


def _show(event: Event) -> None:
    # A response event carries no result - including when the stop reason itself is
    # absent, which the loop reports rather than acts on.
    if event.result is None:
        print(f"iter {event.iteration}  stop_reason={event.stop_reason}")
        return

    mark = "!" if event.result.is_error else " "
    arguments = ", ".join(f"{k}={v!r}" for k, v in (event.tool_input or {}).items())
    print(f"       ->{mark} {event.tool_name}({arguments})")
    print(f"       <-{mark} {event.result.content}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent_loop", description=__doc__)
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT, help="the task to run")
    parser.add_argument("--model", default=None, help="override the model for this run")
    args = parser.parse_args(argv)

    model = resolve_model(args.model)
    print(f"model: {model}\ntask:  {args.prompt}\n")

    try:
        answer = run(args.prompt, model=model, on_event=_show)
    except AgentLoopError as exc:
        print(f"\nno answer: {exc}", file=sys.stderr)
        return 1

    print(f"\nanswer: {answer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
