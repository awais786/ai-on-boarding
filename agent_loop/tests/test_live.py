"""The live-model check, and the report that runs when it cannot be performed.

Written from specs/multi-tool-agent-loop/spec.md. One requirement - *Let the model
choose the tool* - cannot be verified without a live model, because it is a claim
about the model's judgement rather than about this code. When no credential is
present that check does not run, and the run says so.
"""

from __future__ import annotations

import pytest

from agent_loop.loop import Event, run
from agent_loop.tests.conftest import (
    CREDENTIAL,
    REQUIREMENTS_NEEDING_A_LIVE_MODEL,
    has_credential,
    pytest_terminal_summary,
)

TASK = "What is the population of Tokyo divided by 1000?"


# --- Requirements: Let the model choose the tool / Demonstrate the complete lifecycle ---------


@pytest.mark.skipif(not has_credential(), reason=f"needs {CREDENTIAL} - reported in the summary")
def test_the_model_chooses_the_search_then_the_calculation_and_the_run_completes():
    """The whole lifecycle against a live model: choice, execution, result, choice, answer.

    Asserts the sequence of tools the model chose and that the run finished - not the
    wording of the answer, which is the model's to phrase.
    """
    chosen: list[str] = []

    def record(event: Event) -> None:
        if event.tool_name is not None:
            chosen.append(event.tool_name)

    answer = run(TASK, on_event=record)

    assert chosen == ["web_search", "calculator"], (
        f"expected a search then a calculation, the model chose {chosen}"
    )
    assert answer
    assert "14,180" in answer or "14180" in answer


# --- Requirement: Demonstrate the complete lifecycle (the unverified-report half) --------------


class _FakeReporter:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write_sep(self, sep: str, title: str, **kwargs) -> None:
        self.lines.append(title)

    def write_line(self, line: str, **kwargs) -> None:
        self.lines.append(line)


def test_the_run_names_the_unverified_requirements_when_there_is_no_credential(monkeypatch):
    monkeypatch.delenv(CREDENTIAL, raising=False)
    reporter = _FakeReporter()

    pytest_terminal_summary(reporter, exitstatus=0, config=None)

    reported = "\n".join(reporter.lines)
    assert "UNVERIFIED" in reported
    for requirement in REQUIREMENTS_NEEDING_A_LIVE_MODEL:
        assert requirement in reported


def test_nothing_is_reported_as_unverified_when_a_credential_is_present(monkeypatch):
    monkeypatch.setenv(CREDENTIAL, "sk-ant-not-a-real-key")
    reporter = _FakeReporter()

    pytest_terminal_summary(reporter, exitstatus=0, config=None)

    assert reporter.lines == []


def test_the_run_does_not_claim_the_rest_was_verified_when_tests_failed(monkeypatch):
    """Claiming everything else passed while tests are red is the same misreport,
    pointing the other way."""
    monkeypatch.delenv(CREDENTIAL, raising=False)
    reporter = _FakeReporter()

    pytest_terminal_summary(reporter, exitstatus=1, config=None)

    reported = "\n".join(reporter.lines)
    assert "Everything else was verified" not in reported
    assert "NOT all verified" in reported
