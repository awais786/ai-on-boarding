"""Tests for the two tools, written from specs/multi-tool-agent-loop/spec.md."""

from __future__ import annotations

import time

import pytest

from agent_loop.tools import TOOLS, calculator, dispatch, web_search


def _declaration(name: str) -> dict:
    return next(tool for tool in TOOLS if tool["name"] == name)


# --- Requirement: Offer a calculator tool -----------------------------------------------------


def test_the_calculator_is_offered_with_a_description_and_its_input_schema():
    declaration = _declaration("calculator")
    assert declaration["description"].strip()
    schema = declaration["input_schema"]
    assert schema["required"] == ["expression"]
    assert schema["properties"]["expression"]["type"] == "string"


def test_an_arithmetic_expression_is_evaluated():
    assert calculator("14180000 / 1000").content == "14180"
    assert calculator("14180000 / 1000").is_error is False


# --- Requirement: Offer a web search tool -----------------------------------------------------


def test_the_web_search_is_offered_with_a_description_and_its_input_schema():
    declaration = _declaration("web_search")
    assert declaration["description"].strip()
    schema = declaration["input_schema"]
    assert schema["required"] == ["query"]
    assert schema["properties"]["query"]["type"] == "string"


def test_a_known_query_returns_its_stub_result():
    result = web_search("what is the population of Tokyo")
    assert result.is_error is False
    assert "14180000" in result.content


def test_an_unmatched_query_still_returns_a_result_rather_than_failing():
    result = web_search("the airspeed velocity of an unladen swallow")
    assert result.is_error is False
    assert result.content


def test_searching_makes_no_network_request(monkeypatch):
    """The stub must not reach the network - a socket would be a real search."""
    import socket

    def refuse(*args, **kwargs):
        raise AssertionError("web_search attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert web_search("population of Tokyo").content


# --- Requirement: Evaluate expressions without executing arbitrary code -----------------------


@pytest.mark.parametrize(
    "expression",
    [
        "().__class__",
        "__import__('os').system('echo pwned')",
        "open('/etc/passwd')",
        "[x for x in range(3)]",
        "lambda: 1",
        "True and 1",
        "'a' * 3",
    ],
)
def test_an_expression_that_is_not_arithmetic_is_refused(expression):
    result = calculator(expression)
    assert result.is_error is True
    assert "error" in result.content


def test_a_refused_expression_is_never_evaluated(tmp_path):
    """Refusal must happen before evaluation, not by catching the aftermath."""
    marker = tmp_path / "written-by-the-calculator"
    result = calculator(f"open({str(marker)!r}, 'w').write('x')")
    assert result.is_error is True
    assert not marker.exists()


def test_dividing_by_zero_returns_an_error_rather_than_raising():
    result = calculator("1 / 0")
    assert result.is_error is True
    assert "zero" in result.content


def test_an_expression_with_no_finite_value_returns_an_error_rather_than_raising():
    result = calculator("1e308 * 10")
    assert result.is_error is True


def test_a_malformed_expression_returns_an_error_rather_than_raising():
    result = calculator("2 +")
    assert result.is_error is True


@pytest.mark.parametrize(
    "expression",
    [
        "(-8) ** (1 / 3)",  # a negative base to a fractional power is complex, not real
        "(-2) ** 0.5",
        "(-2) ** 0.5 * 0",  # complex propagates through, and would skip the finite check
        "(-8) ** 0.5 // 2",  # a complex intermediate reaching an operator with no complex form
        "(-8) ** 0.5 % 2",
    ],
)
def test_an_expression_with_no_real_value_is_refused(expression):
    result = calculator(expression)
    assert result.is_error is True
    assert "real value" in result.content


# --- Requirement: Refuse an expression whose result would be too large to compute --------------


@pytest.mark.parametrize(
    "expression",
    [
        "2 ** 999999999",
        "(10 ** 1000) ** 1000",  # every exponent is small; nesting is what grows the result
        "((10 ** 1000) ** 1000) ** 1000",
    ],
)
def test_a_power_whose_result_would_be_enormous_is_refused_promptly(expression):
    """Refusal must be predicted. Attempting these and giving up is not an option -
    the memory is claimed before anything could time out. Without the guard this
    expression does not return at all, so a regression stops the suite rather than
    failing it quietly."""
    started = time.monotonic()
    result = calculator(expression)
    elapsed = time.monotonic() - started

    assert result.is_error is True
    assert "too large" in result.content
    assert elapsed < 1.0, f"refusal took {elapsed:.2f}s - it was computed, not predicted"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 ** 10", "1024"),
        ("10 ** 100", "1" + "0" * 100),
        ("2 ** -3", "0.125"),
        ("0 ** 999999999", "0"),  # an enormous exponent that costs nothing
        ("1 ** 999999999", "1"),
    ],
)
def test_ordinary_arithmetic_is_unaffected_by_the_bound(expression, expected):
    result = calculator(expression)
    assert result.is_error is False
    assert result.content == expected


def test_a_power_with_a_float_operand_is_left_to_the_finite_check():
    assert calculator("2 ** 0.5").content.startswith("1.414")
    assert calculator("2.0 ** 100000").is_error is True


# --- Requirement: Execute every requested tool and return its result (dispatch half) -----------


def test_a_requested_tool_runs_with_the_input_the_model_supplied():
    assert dispatch("calculator", {"expression": "6 * 7"}).content == "42"


def test_a_tool_that_does_not_exist_reports_an_error_rather_than_raising():
    result = dispatch("nonexistent_tool", {"anything": 1})
    assert result.is_error is True
    assert "no tool named" in result.content


@pytest.mark.parametrize(
    "tool_input",
    [{}, {"expression": ""}, {"expression": "   "}, {"expression": 42}, "not-an-object", None],
)
def test_input_a_tool_cannot_use_reports_an_error_rather_than_raising(tool_input):
    result = dispatch("calculator", tool_input)
    assert result.is_error is True
