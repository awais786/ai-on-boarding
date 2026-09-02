"""Tool definitions, implementations, and dispatcher for the multi-tool agent loop."""

import ast
import operator

CALCULATOR_TOOL = {
    "name": "calculator",
    "description": (
        "Evaluates a basic arithmetic expression (numbers and + - * / ** ( ) operators only) "
        "and returns the numeric result. Use this whenever a numeric computation is needed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The arithmetic expression to evaluate, e.g. '68000000 * 0.10'.",
            }
        },
        "required": ["expression"],
    },
}

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Searches the web for the given query and returns a short summary of results. "
        "Use this to look up facts you don't already know."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query, e.g. 'France population'.",
            }
        },
        "required": ["query"],
    },
}

TOOLS = [CALCULATOR_TOOL, WEB_SEARCH_TOOL]

_ALLOWED_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

_ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINARY_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        return _ALLOWED_BINARY_OPERATORS[op_type](
            _eval_node(node.left), _eval_node(node.right)
        )
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARY_OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        return _ALLOWED_UNARY_OPERATORS[op_type](_eval_node(node.operand))
    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


def calculator(expression: str) -> str:
    """Evaluate a restricted arithmetic expression and return the result as a string."""
    try:
        parsed = ast.parse(expression, mode="eval")
        result = _eval_node(parsed)
    except Exception as exc:  # noqa: BLE001 - report any parse/eval failure as a tool error
        raise ValueError(f"Could not evaluate expression '{expression}': {exc}") from exc
    return str(result)


_MOCK_SEARCH_RESULTS = {
    ("france", "population"): "France population is 68 million.",
}


def web_search(query: str) -> str:
    """Return a mock/stub search result string for the given query. No network call is made."""
    normalized = query.lower()
    for keywords, result in _MOCK_SEARCH_RESULTS.items():
        if all(keyword in normalized for keyword in keywords):
            return result
    return f"No mock search results available for query: '{query}'."


def dispatch_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Route a tool_use request to its implementation.

    Returns a (result_text, is_error) tuple. An unrecognized tool name produces an
    explicit error result rather than being silently ignored.
    """
    if name == "calculator":
        try:
            return calculator(tool_input["expression"]), False
        except Exception as exc:  # noqa: BLE001 - surface as a tool_result error, not a crash
            return str(exc), True
    if name == "web_search":
        try:
            return web_search(tool_input["query"]), False
        except Exception as exc:  # noqa: BLE001 - surface as a tool_result error, not a crash
            return str(exc), True
    return f"Unrecognized tool: '{name}'", True
