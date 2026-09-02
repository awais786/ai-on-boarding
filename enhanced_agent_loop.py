"""enhanced_agent_loop.py - a second, standalone agent-loop worked example.

Extends the base ask -> dispatch -> observe -> repeat loop (see agent_loop/, a separate
exercise this script does not import from) with three additions in different layers:
a real (non-mocked) `web_search` tool backed by DuckDuckGo's free Instant Answer API,
dispatch-boundary argument validation via `validate_args`, and a few-shot example that
steers tool-choice ordering for ambiguous requests. See
openspec/changes/enhanced-agent-loop/ for the full proposal/spec/design.

Run by hand:
    python enhanced_agent_loop.py "<prompt>"
"""

import ast
import json
import logging
import math
import operator
import sys
import urllib.parse
import urllib.request

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_ITERATIONS = 20

DUCKDUCKGO_URL = "https://api.duckduckgo.com/"
DUCKDUCKGO_TIMEOUT = 5

MAX_EXPRESSION_LENGTH = 200
MAX_QUERY_LENGTH = 500

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
                        'A mathematical expression to evaluate, e.g. "68000000 / 1000".'
                    ),
                }
            },
            "required": ["expression"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Searches the web via DuckDuckGo's Instant Answer API and returns a summary "
            "relevant to the given query."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                }
            },
            "required": ["query"],
        },
    },
]

FEW_SHOT_EXAMPLE = [
    {"role": "user", "content": "What is Japan's population divided by 2?"},
    {
        "role": "assistant",
        "content": (
            "I'll first use web_search to find Japan's population, then use calculator to "
            "divide that number by 2."
        ),
    },
]


# --- calculator: same ast-based whitelist approach as agent_loop/tools.py -----------
# (a separate copy, not an import - see design.md's "self-contained script" decision)

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


def evaluate_expression(expression):
    """Evaluate a string as a pure arithmetic expression, or raise ExpressionError."""
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError(
            f"expression too long (max {MAX_EXPRESSION_LENGTH} characters)"
        )

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid syntax: {exc.msg}") from exc

    try:
        result = _eval_node(tree)
    except ArithmeticError as exc:
        raise ExpressionError(str(exc)) from exc
    except RecursionError as exc:
        raise ExpressionError("expression too deeply nested") from exc

    if not math.isfinite(result):
        raise ExpressionError(f"result is not finite: {result!r}")

    return result


def calculator(expression):
    try:
        result = evaluate_expression(expression)
    except ExpressionError as exc:
        return {"error": str(exc)}
    return {"result": result}


# --- web_search: real DuckDuckGo Instant Answer API, never raises -------------------

def web_search(query):
    url = DUCKDUCKGO_URL + "?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "no_html": "1"}
    )
    try:
        with urllib.request.urlopen(url, timeout=DUCKDUCKGO_TIMEOUT) as response:
            body = response.read()
        data = json.loads(body)
    except Exception as exc:
        # Deliberately broad: URLError/TimeoutError/JSONDecodeError are the anticipated cases,
        # but a socket read can also raise ConnectionResetError, http.client.IncompleteRead, or
        # UnicodeDecodeError (json.loads decoding non-UTF-8 bytes) - none of which subclass the
        # three above. The spec requires web_search to never raise "for any failure mode," not
        # just the enumerated ones, so every exception at this boundary is caught here.
        return {"error": f"web_search failed ({type(exc).__name__}): {exc}"}

    abstract = (data.get("AbstractText") or "").strip()
    if abstract:
        return {"result": abstract}
    return {"result": f"No summary available for '{query}'."}


# --- dispatch: validate_args runs before either tool ever executes ------------------

def validate_args(name, args):
    """Validate a tool call's arguments before dispatch executes the real tool.

    Returns None when valid, or an error string when not - dispatch short-circuits on a
    non-None result rather than calling calculator/web_search at all, so a malformed call
    never reaches - and never depends on - either tool's own internal error handling.
    """
    if name == "calculator":
        field, max_length = "expression", MAX_EXPRESSION_LENGTH
    elif name == "web_search":
        field, max_length = "query", MAX_QUERY_LENGTH
    else:
        return f"unknown tool: {name}"

    value = args.get(field) if isinstance(args, dict) else None
    if not isinstance(value, str) or not value.strip():
        return f"invalid {field}: must be a non-empty string"
    if len(value) > max_length:
        return f"invalid {field}: exceeds maximum length of {max_length} characters"
    return None


_TOOL_FUNCTIONS = {
    "calculator": lambda args: calculator(args["expression"]),
    "web_search": lambda args: web_search(args["query"]),
}


def dispatch(name, args):
    validation_error = validate_args(name, args)
    if validation_error is not None:
        return {"error": validation_error}

    handler = _TOOL_FUNCTIONS.get(name)
    if handler is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return handler(args)
    except (KeyError, TypeError, AttributeError) as exc:
        return {"error": f"invalid input for tool {name!r}: {exc}"}


# --- loop: ask -> dispatch -> observe -> repeat, terminating only on end_turn -------

def _extract_text(content_blocks):
    return "".join(block.text for block in content_blocks if block.type == "text")


def run_agent_loop(client, prompt, max_iterations=MAX_ITERATIONS, on_event=None):
    """Drive a tool-use conversation with Claude until it signals end_turn.

    The few-shot example (one user/assistant pair demonstrating web_search -> calculator
    ordering) is prepended before `prompt` on every call. Returns `(final_text, tool_calls,
    terminated_via)`, matching agent_loop/loop.py's `run_agent_loop` contract.
    """
    emit = on_event if on_event is not None else lambda event: None
    messages = list(FEW_SHOT_EXAMPLE) + [{"role": "user", "content": prompt}]
    tool_calls = []
    text = ""

    for _ in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )

        text = _extract_text(response.content)
        if text:
            emit({"type": "text", "text": text})

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            tool_results = []
            for block in tool_use_blocks:
                tool_calls.append({"name": block.name, "input": block.input})
                outcome = dispatch(block.name, block.input)
                is_error = "error" in outcome
                content_text = str(outcome["error"] if is_error else outcome["result"])
                emit(
                    {
                        "type": "action",
                        "name": block.name,
                        "input": block.input,
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
                "enhanced_agent_loop: unexpected stop_reason %r, returning best-effort text",
                response.stop_reason,
            )
            emit({"type": "terminated", "stop_reason": response.stop_reason})
        return text, tool_calls, response.stop_reason

    logger.warning(
        "enhanced_agent_loop: MAX_ITERATIONS (%d) reached without end_turn", max_iterations
    )
    emit({"type": "max_iterations"})
    return text, tool_calls, "max_iterations"


# --- CLI entry point -----------------------------------------------------------------

def _format_call(name, tool_input):
    if len(tool_input) == 1:
        (value,) = tool_input.values()
        return f'{name}("{value}")' if isinstance(value, str) else f"{name}({value})"
    return f"{name}({tool_input})"


def _print_event(event):
    etype = event["type"]
    if etype == "text":
        print(f'\nClaude:\n"{event["text"]}"')
    elif etype == "action":
        call = _format_call(event["name"], event["input"])
        label = "error" if event["is_error"] else "result"
        print(f"\n[action] {call}\n{label}: {event['content']}")
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
        print('usage: python enhanced_agent_loop.py "<prompt>"', file=sys.stderr)
        raise SystemExit(1)

    prompt = argv[0]
    print(f'User:\n"{prompt}"')

    client = anthropic.Anthropic()
    run_agent_loop(client, prompt, on_event=_print_event)


if __name__ == "__main__":
    main()
