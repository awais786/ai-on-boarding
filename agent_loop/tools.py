"""Tool definitions and implementations for the multi-tool agent loop.

Two tools are exposed to Claude: `calculator` (safe arithmetic evaluation) and
`web_search` (a stubbed lookup - no real network search is performed).
"""

import ast
import operator

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
    {
        "name": "web_search",
        "description": (
            "Searches the web for information relevant to the given query and returns a "
            "summary of the results."
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
        return _eval_node(tree)
    except ArithmeticError as exc:
        # covers ZeroDivisionError and OverflowError (e.g. a huge integer literal
        # multiplied into a float)
        raise ExpressionError(str(exc)) from exc
    except RecursionError as exc:
        raise ExpressionError("expression too deeply nested") from exc


def calculator(expression):
    try:
        result = evaluate_expression(expression)
    except ExpressionError as exc:
        return {"error": str(exc)}
    return {"result": result}


_MOCK_SEARCH_RESULTS = {
    "france population": "France's population is approximately 68 million (2023 estimate).",
}


def web_search(query):
    result = _MOCK_SEARCH_RESULTS.get(query.strip().lower())
    if result is None:
        result = f"No mock results available for '{query}'."
    return {"result": result}


_TOOL_FUNCTIONS = {
    "calculator": lambda tool_input: calculator(tool_input["expression"]),
    "web_search": lambda tool_input: web_search(tool_input["query"]),
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
