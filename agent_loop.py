"""agent_loop.py - the base multi-tool agent-loop worked example.

Drives Claude through tool_use round trips until it signals end_turn, never inferring
completion any other way. Two tools are exposed: `calculator`, a client tool implemented and
dispatched here (safe arithmetic evaluation), and `web_search`, Anthropic's provider-executed
server tool - declared in TOOLS but executed by Anthropic's servers, so there is no handler for
it here. See openspec/changes/42-multi-tool-claude-agent-loop/ for the full proposal/spec/design.

Run by hand:
    python -m agent_loop "<prompt>"
"""

import ast
import logging
import math
import operator
import sys

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_ITERATIONS = 20

TOOLS = [
    {
        "name": "calculator",
        "description": (
            "Evaluates a mathematical expression (addition, subtraction, multiplication, "
            "division, modulo, parentheses) and returns the numeric result. Cannot execute "
            "arbitrary code - only arithmetic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "A mathematical expression to evaluate, e.g. \"68000000 * 0.10\"."
                    ),
                }
            },
            "required": ["expression"],
        },
    },
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 3},
]


# --- calculator: ast-based safe-eval whitelist, no arbitrary code execution ---------

_ALLOWED_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}

_ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class ExpressionError(ValueError):
    """The given expression is not a valid arithmetic expression."""


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ExpressionError(f"unsupported constant: {node.value!r}")
        return node.value

    if isinstance(node, ast.BinOp):
        op_impl = _ALLOWED_BINARY_OPERATORS.get(type(node.op))
        if op_impl is None:
            raise ExpressionError(f"unsupported operator: {type(node.op).__name__}")
        return op_impl(_eval_node(node.left), _eval_node(node.right))

    if isinstance(node, ast.UnaryOp):
        op_impl = _ALLOWED_UNARY_OPERATORS.get(type(node.op))
        if op_impl is None:
            raise ExpressionError(f"unsupported operator: {type(node.op).__name__}")
        return op_impl(_eval_node(node.operand))

    raise ExpressionError(f"unsupported expression element: {type(node).__name__}")


_MAX_EXPRESSION_LENGTH = 200


def evaluate_expression(expression):
    """Evaluate a string as a pure arithmetic expression, or raise ExpressionError."""
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ExpressionError(
            f"expression too long (max {_MAX_EXPRESSION_LENGTH} characters)"
        )

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid syntax: {exc.msg}") from exc

    try:
        result = _eval_node(tree)
    except ArithmeticError as exc:
        # covers ZeroDivisionError and OverflowError (e.g. a huge integer literal
        # multiplied into a float)
        raise ExpressionError(str(exc)) from exc
    except RecursionError as exc:
        raise ExpressionError("expression too deeply nested") from exc

    if not math.isfinite(result):
        # a scientific-notation literal like "1e400" overflows to inf during
        # ast.parse() itself, before any node is evaluated, so it must be
        # caught here rather than via ArithmeticError above
        raise ExpressionError(f"result is not finite: {result!r}")

    return result


def calculator(expression):
    try:
        result = evaluate_expression(expression)
    except ExpressionError as exc:
        return {"error": str(exc)}
    return {"result": result}


# --- dispatch: client-tool execution; web_search is provider-executed, no handler here --

_TOOL_FUNCTIONS = {
    "calculator": lambda tool_input: calculator(tool_input["expression"]),
}


def dispatch(name, tool_input):
    """Execute the named tool with the given input, returning {"result": ...} or {"error": ...}.

    Always returns one of those two shapes - it never raises - so a malformed
    tool_input (a missing required field, or a field of the wrong type) comes
    back as an error result Claude can see and react to, rather than crashing
    the loop that called it.
    """
    handler = _TOOL_FUNCTIONS.get(name)
    if handler is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return handler(tool_input)
    except (KeyError, TypeError, AttributeError) as exc:
        return {"error": f"invalid input for tool {name!r}: {exc}"}


# --- loop: ask -> dispatch -> observe -> repeat, terminating only on end_turn -------


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
            tools=TOOLS,
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
                    outcome = dispatch(block.name, block.input)
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


# --- CLI entry point -----------------------------------------------------------------


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
