from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from issue_reconciler.policy.rules import decide_action

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "issues_snapshot.json"
SCENARIOS = json.loads(FIXTURES_PATH.read_text())


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_policy_scenarios(scenario):
    decision = decide_action(scenario["evidence"], now=datetime.fromisoformat(scenario["now"]))
    assert decision == scenario["expected"]
