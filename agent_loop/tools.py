"""The tools the model can choose between, and the dispatch that runs them.

A tool never raises at the loop's boundary. Anything that goes wrong - an unknown
tool, input the tool cannot use, an expression that refuses to evaluate - comes
back as a `ToolResult` marked as an error, so the model can read what went wrong
and respond to it rather than the run ending.
"""

from __future__ import annotations

import ast
import math
import operator
from dataclasses import dataclass
from typing import Any, Callable

CALCULATOR = "calculator"
WEB_SEARCH = "web_search"


@dataclass(frozen=True)
class ToolResult:
    """What a tool hands back to the loop."""

    content: str
    is_error: bool = False


# --- calculator ------------------------------------------------------------------------------
#
# The expression is parsed into a syntax tree and walked, rather than evaluated. Only numbers,
# the arithmetic operators and the grouping the parser already resolved are permitted; a name,
# an attribute, a subscript or a call has no branch here and is refused before anything runs.

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


MAX_RESULT_BITS = 4096
"""Roughly 1,200 decimal digits - far beyond any arithmetic this tool exists to do."""


class _Refused(Exception):
    """The expression contains something the calculator will not evaluate."""


def _refuse_unbounded_power(base: int | float, exponent: int | float) -> None:
    """Refuse a power whose result would be enormous - predicted, never attempted.

    `2 ** 999999999` is arithmetic, reaches nothing, and has a finite value; it simply
    never returns. The size is predicted from the base's bit length so that nesting is
    bounded too - each level is checked against the value the level below produced.
    Floats are left alone: they overflow to infinity, which the caller already refuses.
    """
    if not (isinstance(base, int) and isinstance(exponent, int)):
        return
    if exponent < 0 or base in (0, 1, -1):
        return
    if base.bit_length() * exponent > MAX_RESULT_BITS:
        raise _Refused(
            f"a result of about {base.bit_length() * exponent} bits is too large to compute"
        )


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant):
        # bool is a subclass of int; True + 1 is not arithmetic anyone asked for.
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise _Refused(f"{type(node.value).__name__} is not a number")
        return node.value

    if isinstance(node, ast.BinOp):
        apply = _BINARY_OPERATORS.get(type(node.op))
        if apply is None:
            raise _Refused(f"{type(node.op).__name__} is not an arithmetic operator")
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow):
            _refuse_unbounded_power(left, right)
        return apply(left, right)

    if isinstance(node, ast.UnaryOp):
        apply_unary = _UNARY_OPERATORS.get(type(node.op))
        if apply_unary is None:
            raise _Refused(f"{type(node.op).__name__} is not an arithmetic operator")
        return apply_unary(_evaluate(node.operand))

    raise _Refused(f"{type(node).__name__} is not arithmetic")


def _format(value: int | float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def calculator(expression: str) -> ToolResult:
    """Evaluate an arithmetic expression, refusing anything that is not arithmetic."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return ToolResult(f"error: {expression!r} is not a valid expression ({exc.msg})", True)

    try:
        value = _evaluate(tree.body)
    except _Refused as exc:
        return ToolResult(f"error: refused to evaluate {expression!r} - {exc}", True)
    except ZeroDivisionError:
        return ToolResult(f"error: {expression!r} divides by zero", True)
    except (OverflowError, ValueError) as exc:
        return ToolResult(f"error: {expression!r} has no value ({exc})", True)
    except TypeError:
        # A complex intermediate - from a negative base to a fractional power - reaching an
        # operator that has no complex form, such as `(-8) ** 0.5 // 2`. The guard below
        # inspects the final value, which this never reaches.
        return ToolResult(f"error: {expression!r} has no real value", True)

    # A negative base raised to a fractional power gives a complex number, which is a
    # value but not one this tool answers with - and complex skips the finite check below.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ToolResult(f"error: {expression!r} has no real value", True)

    if isinstance(value, float) and not math.isfinite(value):
        return ToolResult(f"error: {expression!r} has no finite value", True)

    return ToolResult(_format(value))


# --- web search ------------------------------------------------------------------------------
#
# Stub results. Nothing here reaches the network: the point of this tool is to give the model a
# value it was not told, so a task can require a lookup before a calculation.

_STUB_RESULTS: dict[str, str] = {
    "tokyo": "Tokyo metropolitan population: 14180000 (stub result)",
    "london": "Greater London population: 8866000 (stub result)",
    "paris": "Paris city population: 2103000 (stub result)",
    "france": "France population: 68400000 (stub result)",
    "japan": "Japan population: 123300000 (stub result)",
}


def web_search(query: str) -> ToolResult:
    """Return a stub search result for a query, without touching the network."""
    lowered = query.lower()
    for term, result in _STUB_RESULTS.items():
        if term in lowered:
            return ToolResult(result)
    return ToolResult(f"No stub result is held for {query!r} (stub result)")


# --- declarations and dispatch ---------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": WEB_SEARCH,
        "description": (
            "Search the web for a fact you do not already know, such as a population, a price, "
            "or any current value. Call this before doing arithmetic on a value you were not "
            "given in the question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for."},
            },
            "required": ["query"],
        },
    },
    {
        "name": CALCULATOR,
        "description": (
            "Evaluate an arithmetic expression and return its value. Call this whenever a "
            "calculation is needed, rather than working the arithmetic out yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "An arithmetic expression, for example '14180000 / 1000'.",
                },
            },
            "required": ["expression"],
        },
    },
]

# Each entry is the tool's function and the name of the single input it reads.
_HANDLERS: dict[str, tuple[Callable[[str], ToolResult], str]] = {
    CALCULATOR: (calculator, "expression"),
    WEB_SEARCH: (web_search, "query"),
}


def dispatch(name: str, tool_input: Any) -> ToolResult:
    """Run the named tool against the input the model supplied.

    Returns an error result rather than raising, whatever the model asked for.
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        known = ", ".join(sorted(_HANDLERS))
        return ToolResult(f"error: there is no tool named {name!r} (available: {known})", True)

    run, field = handler
    if not isinstance(tool_input, dict):
        return ToolResult(f"error: {name} needs an object of arguments, not {tool_input!r}", True)

    value = tool_input.get(field)
    if not isinstance(value, str) or not value.strip():
        return ToolResult(f"error: {name} needs a non-empty {field!r} string", True)

    try:
        return run(value)
    except Exception as exc:  # a tool must never end the run by raising
        return ToolResult(f"error: {name} failed on {value!r} ({type(exc).__name__}: {exc})", True)
