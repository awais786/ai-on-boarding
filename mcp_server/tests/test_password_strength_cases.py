"""Runs the same case list sdd_django_demo/api/test_password_strength_cases.py runs,
against backend_client's mirror of Django's password rule.

One shared fixture (sdd_django_demo/api/password_strength_cases.json), read from both
suites, means the two rules drifting apart shows up as a failing test on whichever
side changed, rather than silently - see that file's own docstring.
"""

import json
from pathlib import Path

import pytest

import backend_client

CASES_PATH = (
    Path(__file__).resolve().parents[2] / 'sdd_django_demo' / 'api' / 'password_strength_cases.json'
)
CASES = json.loads(CASES_PATH.read_text())


@pytest.mark.parametrize('case', CASES, ids=[c['password'] or '(empty)' for c in CASES])
def test_password_strength_cases(case):
    if case['valid']:
        backend_client.validate_password_strength(case['password'])  # must not raise
    else:
        with pytest.raises(backend_client.BackendAPIError):
            backend_client.validate_password_strength(case['password'])
