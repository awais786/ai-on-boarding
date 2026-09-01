"""Run the multi-tool agent loop by hand: python -m agent_loop "<prompt>"

Prints the running transcript - Claude's narration, each tool_use call, and
each tool_result - in the same shape as the worked example in issue #42.
"""

import sys

import anthropic

from .loop import run_agent_loop


def _format_tool_call(name, tool_input):
    if len(tool_input) == 1:
        (value,) = tool_input.values()
        return f'{name}("{value}")' if isinstance(value, str) else f"{name}({value})"
    return f"{name}({tool_input})"


def _print_event(event):
    etype = event["type"]
    if etype == "text":
        print(f'\nClaude:\n"{event["text"]}"')
    elif etype == "tool_use":
        print(f"\ntool_use:\n{_format_tool_call(event['name'], event['input'])}")
    elif etype == "tool_result":
        print(f'\ntool_result:\n"{event["content"]}"')
    elif etype == "end_turn":
        print("\nend_turn")
    elif etype == "max_iterations":
        print("\n[warning] MAX_ITERATIONS reached without end_turn", file=sys.stderr)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print('usage: python -m agent_loop "<prompt>"', file=sys.stderr)
        raise SystemExit(1)

    prompt = argv[0]
    print(f'User:\n"{prompt}"')

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": prompt}]

    _, _, terminated_via = run_agent_loop(client, messages, on_event=_print_event)

    if terminated_via not in ("end_turn", "max_iterations"):
        print(f"\n[warning] terminated via {terminated_via!r}, not end_turn", file=sys.stderr)


if __name__ == "__main__":
    main()
