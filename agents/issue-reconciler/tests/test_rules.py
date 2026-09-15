from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from issue_reconciler.rules import apply_verdicts, decide_action

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "issues_snapshot.json"
SCENARIOS = json.loads(FIXTURES_PATH.read_text())


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_policy_scenarios(scenario):
    decision = decide_action(scenario["evidence"], now=datetime.fromisoformat(scenario["now"]))
    assert decision == scenario["expected"]


def test_apply_verdicts_passes_through_when_no_verdict_disagrees():
    decision = {"action": "set_done", "reason": "PR merged, none open"}
    assert apply_verdicts(decision, {}) == decision


def test_apply_verdicts_downgrades_set_done_on_incomplete_coverage():
    decision = {"action": "set_done", "reason": "PR merged, none open"}
    verdicts = {"completion": {"fully_resolved": False, "reasoning": "x"}}
    result = apply_verdicts(decision, verdicts)
    assert result["action"] == "flag"


def test_apply_verdicts_downgrades_on_superseded_pr():
    decision = {"action": "set_done", "reason": "PR merged, none open"}
    verdicts = {"stale": {"superseded": True, "reasoning": "x"}}
    assert apply_verdicts(decision, verdicts)["action"] == "flag"


def test_apply_verdicts_downgrades_set_in_progress_on_abandoned_pr():
    decision = {"action": "set_in_progress", "reason": "PR open"}
    verdicts = {"activity": {"status": "abandoned", "reasoning": "x"}}
    assert apply_verdicts(decision, verdicts)["action"] == "flag"


def test_apply_verdicts_downgrades_on_mismatched_reference_regardless_of_action():
    decision = {"action": "set_done", "reason": "PR merged, none open"}
    verdicts = {"reference": {"matches": False, "reasoning": "x"}}
    assert apply_verdicts(decision, verdicts)["action"] == "flag"


def test_apply_verdicts_never_touches_flag_or_noop():
    for action in ("flag", "noop"):
        decision = {"action": action, "reason": "x"}
        verdicts = {"completion": {"fully_resolved": False, "reasoning": "x"}}
        assert apply_verdicts(decision, verdicts) == decision
