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
        call = _format_tool_call(event["name"], event["input"])
        if event["batch_size"] > 1:
            print(
                f"\ntool_use ({event['batch_index']} of {event['batch_size']} requested "
                f"together):\n{call}"
            )
        else:
            print(f"\ntool_use:\n{call}")
    elif etype == "tool_result":
        print(f'\ntool_result:\n"{event["content"]}"')
    elif etype == "server_tool_use":
        call = _format_tool_call(event["name"], event["input"])
        print(f"\nserver_tool_use (executed by Anthropic, not this code):\n{call}")
    elif etype == "web_search_result":
        if event["is_error"]:
            print(f'\nweb_search_result (error):\n{event["content"]}')
        else:
            print(f'\nweb_search_result:\n{event["content"]}')
    elif etype == "pause_turn":
        print("\n[info] server paused a long-running turn - resending to continue")
    elif etype == "end_turn":
        print("\nend_turn")
    elif etype == "terminated":
        print(
            f"\n[warning] terminated via {event['stop_reason']!r}, not end_turn",
            file=sys.stderr,
        )
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

    run_agent_loop(client, messages, on_event=_print_event)


if __name__ == "__main__":
    main()
