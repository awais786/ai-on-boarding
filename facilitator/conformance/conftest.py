"""Shared fixtures for the conformance suite.

Black-box: the suite speaks HTTP to a running server and knows nothing about the learner's
project layout, models or framework configuration.

Every request shape comes from a payload the facilitator supplies, taken from the learner's
specification. Nothing here hardcodes a field list, because change requests add fields whose
names each learner chooses.
"""

import copy
import json
import uuid

import pytest
import requests


def pytest_addoption(parser):
    parser.addoption("--base-url", default="http://127.0.0.1:8000",
                     help="Base URL of the learner's running server.")
    parser.addoption("--signup-path", default="/api/auth/signup/",
                     help="Signup path, if their specification chose a different one.")
    parser.addoption("--signin-path", default="/api/auth/signin/",
                     help="Signin path, if their specification chose a different one.")
    parser.addoption(
        "--signup-payload",
        default='{"username": "conformance", "email": "conformance@example.com",'
                ' "password": "Conformance-Check-2026!"}',
        help="A valid signup body, as JSON, copied from the learner's specification. "
             "Include every field their spec requires — change requests add fields.",
    )
    parser.addoption(
        "--signin-payload",
        default='{"username": "conformance", "password": "Conformance-Check-2026!"}',
        help="A valid signin body, as JSON, copied from the learner's specification.",
    )
    parser.addoption("--username-field", default="username")
    parser.addoption("--email-field", default="email")
    parser.addoption("--password-field", default="password")
    parser.addoption("--identifier-field", default="username",
                     help="The signin field carrying the identifier. After the email-signin "
                          "change request some learners rename this.")


def _opt(request, name):
    return request.config.getoption(name)


@pytest.fixture(scope="session")
def base_url(request):
    return _opt(request, "--base-url").rstrip("/")


@pytest.fixture(scope="session")
def signup_url(request, base_url):
    return base_url + _opt(request, "--signup-path")


@pytest.fixture(scope="session")
def signin_url(request, base_url):
    return base_url + _opt(request, "--signin-path")


@pytest.fixture(scope="session")
def fields(request):
    return {
        "username": _opt(request, "--username-field"),
        "email": _opt(request, "--email-field"),
        "password": _opt(request, "--password-field"),
        "identifier": _opt(request, "--identifier-field"),
    }


@pytest.fixture(scope="session")
def signup_template(request):
    return json.loads(_opt(request, "--signup-payload"))


@pytest.fixture(scope="session")
def signin_template(request):
    return json.loads(_opt(request, "--signin-payload"))


@pytest.fixture(scope="session", autouse=True)
def server_is_up(base_url):
    try:
        requests.get(base_url, timeout=5)
    except requests.exceptions.RequestException as exc:
        pytest.exit(f"No server reachable at {base_url}: {exc}", returncode=1)


@pytest.fixture
def fresh_signup(signup_template, fields):
    """The facilitator's payload with a unique username and email, so runs never collide."""
    payload = copy.deepcopy(signup_template)
    token = uuid.uuid4().hex[:12]
    payload[fields["username"]] = f"user{token}"
    payload[fields["email"]] = f"conformance-{token}@example.com"
    return payload


@pytest.fixture
def registered(signup_url, fresh_signup):
    """Register a user and hand back the payload it was created with."""
    response = post(signup_url, fresh_signup)
    if not (200 <= response.status_code < 300):
        pytest.fail(
            f"Setup failed — could not register a user for the signin tests. "
            f"Signup returned {response.status_code}: {response.text[:300]}\n"
            f"If their spec requires fields this payload lacks, pass a complete "
            f"--signup-payload."
        )
    return fresh_signup


def post(url, payload):
    return requests.post(url, json=payload, timeout=10)


def without(payload, key):
    stripped = copy.deepcopy(payload)
    stripped.pop(key, None)
    return stripped


def replacing(payload, key, value):
    changed = copy.deepcopy(payload)
    changed[key] = value
    return changed
