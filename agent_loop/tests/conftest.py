"""Test scaffolding: a stub model client, response builders, and the unverified-requirement report.

The stub lets the loop be driven through every path without a credential by scripting
what the model asks for. It records each request it was sent, so a test can assert what
the loop put in the conversation rather than only what it returned.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

CREDENTIAL = "ANTHROPIC_API_KEY"

REQUIREMENTS_NEEDING_A_LIVE_MODEL = [
    "Let the model choose the tool",
    "Demonstrate the complete lifecycle against a live model",
]


def has_credential() -> bool:
    return bool(os.environ.get(CREDENTIAL))


# --- building responses ----------------------------------------------------------------------


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def thinking_block(thinking: str = "", signature: str = "sig") -> SimpleNamespace:
    return SimpleNamespace(type="thinking", thinking=thinking, signature=signature)


def tool_use_block(name: str, tool_input: dict[str, Any], id: str = "req-1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=tool_input)


def response(stop_reason: str, content: list[Any]) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=content)


def requesting(*blocks: Any) -> SimpleNamespace:
    return response("tool_use", list(blocks))


def finished(text: str = "done") -> SimpleNamespace:
    return response("end_turn", [text_block(text)])


# --- the stub client -------------------------------------------------------------------------


class StubClient:
    """Returns scripted responses and records what it was asked."""

    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    @property
    def messages(self) -> "StubClient":
        return self

    def create(self, **kwargs: Any) -> Any:
        # The loop keeps appending to the same list, so snapshot it to see what was sent now.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        if not self._responses:
            raise AssertionError("the loop made more requests than the stub was given")
        return self._responses.pop(0)

    @property
    def conversation(self) -> list[dict[str, Any]]:
        """The conversation as it stood on the most recent request."""
        return self.requests[-1]["messages"]


@pytest.fixture
def stub() -> type[StubClient]:
    return StubClient


# --- reporting what was not verified ----------------------------------------------------------


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:  # noqa: ARG001
    """Say plainly which requirements went unverified, rather than passing over them.

    A suite that reports success having quietly stopped checking something is read as
    evidence that it checked. If the live model could not be reached, the run names the
    requirements that were therefore not verified.
    """
    if has_credential():
        return

    terminalreporter.write_sep("=", "unverified requirements", yellow=True, bold=True)
    terminalreporter.write_line(
        f"{CREDENTIAL} is not set, so the live lifecycle check did not run."
    )
    for requirement in REQUIREMENTS_NEEDING_A_LIVE_MODEL:
        terminalreporter.write_line(f"  UNVERIFIED  Requirement: {requirement}")

    # Claiming the rest was verified while tests were failing would be the same
    # misreport this summary exists to prevent, in the other direction.
    if exitstatus == 0:
        terminalreporter.write_line(
            "Everything else was verified. Set the credential to verify these two."
        )
    else:
        terminalreporter.write_line(
            "Other requirements were NOT all verified either - this run has failures above."
        )
