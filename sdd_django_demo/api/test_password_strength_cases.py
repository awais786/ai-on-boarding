"""Runs password_strength_cases.json against this project's own password rule.

mcp_server mirrors this same rule (its own copy of the check, so a weak password is
rejected before a network round trip) and runs the identical case list in
mcp_server/tests/test_password_strength_cases.py. Keeping one shared fixture, run by
both suites, means the two rules drifting apart shows up as a failing test on
whichever side changed, rather than silently.
"""

import json
from pathlib import Path

import pytest
from rest_framework import serializers

from .serializers import validate_password_strength

CASES = json.loads((Path(__file__).parent / 'password_strength_cases.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=[c['password'] or '(empty)' for c in CASES])
def test_password_strength_cases(case):
    if case['valid']:
        validate_password_strength(case['password'])  # must not raise
    else:
        with pytest.raises(serializers.ValidationError):
            validate_password_strength(case['password'])
