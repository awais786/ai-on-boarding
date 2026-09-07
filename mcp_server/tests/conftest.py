"""Fixtures for the session-auth tests.

Every fixture here is a stand-in for something across the network - Google, or the
Django API. No test in this directory makes a real request, and each fake counts
what it was asked to do, so a test can assert on how many times Google or Django
was called, which is most of what this change is about.
"""

import os
import secrets
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# server.py reads these at import time to build the GoogleProvider.
os.environ.setdefault('GOOGLE_CLIENT_ID', 'test-client-id.apps.googleusercontent.com')
os.environ.setdefault('GOOGLE_CLIENT_SECRET', 'test-client-secret')

from fastmcp.server.auth.auth import AccessToken  # noqa: E402
from mcp.types import ElicitResult  # noqa: E402

import django_client  # noqa: E402
import secret_pages  # noqa: E402
import server  # noqa: E402
import session  # noqa: E402

# auth.jwt_issuer (used to sign every session token) is only built once
# get_routes() runs - normally triggered by actually serving the app. Force
# that here, once, so every test can use it regardless of which file runs
# first (a real server always does this before taking its first request).
server.mcp.http_app()


@pytest.fixture(autouse=True)
def _fresh_secret_pages():
    """secret_pages._pending is module-level state shared across every test - clear
    it before and after each test so a leaked or stale pending request from one
    test can never be found by another."""
    secret_pages._pending.clear()
    yield
    secret_pages._pending.clear()


def google_access_token(google_token, subject='google-sub-1'):
    """What a real GoogleTokenVerifier returns for a token Google accepts."""
    return AccessToken(
        token=google_token,
        client_id=subject,
        scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email'],
        expires_at=int(time.time()) + 3600,
        subject=subject,
        claims={'sub': subject, 'email': f'{subject}@example.com'},
    )


class FakeGoogleVerifier:
    """Stands in for GoogleTokenVerifier - i.e. Google itself."""

    def __init__(self):
        self.calls = []
        self.refuse = set()
        self.subjects = {}

    async def verify_token(self, token):
        self.calls.append(token)
        if token in self.refuse:
            return None
        return google_access_token(token, self.subjects.get(token, 'google-sub-1'))

    @property
    def call_count(self):
        return len(self.calls)


class FakeDjango:
    """The Django API, as django_client sees it."""

    def __init__(self):
        self.exchanges = []
        self.calls = []
        self.tokens_for = {}
        self.next_tokens = []
        self.exchange_error = None
        self.rejects = set()
        self.error = None
        self.signup_error = None
        self.reset_error = None
        self.change_own_password_error = None

    async def exchange_google_token(self, google_token):
        self.exchanges.append(google_token)
        if self.exchange_error is not None:
            raise self.exchange_error
        if self.next_tokens:
            return self.next_tokens.pop(0)
        return self.tokens_for.get(google_token, f'drf-for-{google_token}')

    async def list_users(self, django_token, country=None):
        self._check(django_token, ('list_users', django_token, country))
        rows = [{'username': 'ada', 'country': 'GB', 'date_joined': '2026-01-01'}]
        return [r for r in rows if country is None or r['country'] == country]

    async def change_password(self, django_token, username, new_password):
        self._check(django_token, ('change_password', django_token, username))
        return {'detail': 'Password changed.'}

    async def signup(self, email, username, password, country):
        self.calls.append(('signup', email, username, country))
        if self.signup_error is not None:
            raise self.signup_error
        return {'detail': 'Account created.'}

    async def request_password_reset(self, email):
        self.calls.append(('request_password_reset', email))
        return {'detail': 'If that email address has an account, a reset link has been sent to it.'}

    async def confirm_password_reset(self, code, new_password):
        self.calls.append(('confirm_password_reset', code))
        if self.reset_error is not None:
            raise self.reset_error
        return {'detail': 'Password changed.'}

    async def change_own_password(self, django_token, current_password, new_password):
        self._check(django_token, ('change_own_password', django_token))
        if self.change_own_password_error is not None:
            raise self.change_own_password_error
        return {'detail': 'Password changed.'}

    def _check(self, django_token, record):
        self.calls.append(record)
        if django_token in self.rejects:
            raise django_client.DjangoAPIError('Invalid token.', stale_credential=True)
        if self.error is not None:
            raise self.error

    @property
    def exchange_count(self):
        return len(self.exchanges)


@pytest.fixture
def google(monkeypatch):
    """DjangoGoogleProvider._extract_upstream_claims calls self._token_validator
    directly (there's no wrapper around it any more), so this replaces that
    attribute outright rather than patching an inner delegate."""
    fake = FakeGoogleVerifier()
    monkeypatch.setattr(server.auth, '_token_validator', fake)
    return fake


@pytest.fixture
def django(monkeypatch):
    """FakeDjango's own methods keep the (self, django_token, ...) shape the
    module-level functions used to have; these three adapters bridge that to
    AuthedDjangoClient's real (self, ...) shape, reading the token off the real
    client instance django hands them - FakeDjango itself doesn't need to change."""
    fake = FakeDjango()
    for name in ('exchange_google_token', 'signup', 'request_password_reset', 'confirm_password_reset'):
        monkeypatch.setattr(django_client, name, getattr(fake, name))

    async def _list_users(client, country=None):
        return await fake.list_users(client.django_token, country=country)

    async def _change_password(client, username, new_password):
        return await fake.change_password(client.django_token, username, new_password)

    async def _change_own_password(client, current_password, new_password):
        return await fake.change_own_password(client.django_token, current_password, new_password)

    monkeypatch.setattr(django_client.AuthedDjangoClient, 'list_users', _list_users)
    monkeypatch.setattr(django_client.AuthedDjangoClient, 'change_password', _change_password)
    monkeypatch.setattr(django_client.AuthedDjangoClient, 'change_own_password', _change_own_password)
    return fake


@pytest.fixture
def sign_in(google, django, monkeypatch):
    """Sign a caller in exactly the way a real login does - through
    DjangoGoogleProvider's own _extract_upstream_claims and load_access_token,
    with a real signed JWT in between - and make the result the session the
    tools see.

    Returns the AccessToken FastMCP would hand the tools, or None if Google
    itself refused the token - which is what makes them unable to reach any tool.
    """

    async def _sign_in(google_token='google-token-1'):
        try:
            claims = await server.auth._extract_upstream_claims({'access_token': google_token})
        except RuntimeError:
            return None  # Google refused the token being exchanged at login

        jwt = server.auth.jwt_issuer.issue_access_token(
            client_id='test-client',
            scopes=['openid', 'email'],
            jti=secrets.token_urlsafe(8),
            upstream_claims=claims,
            subject=claims.get('sub'),
        )
        verified = await server.auth.load_access_token(jwt)
        monkeypatch.setattr(session, 'get_access_token', lambda: verified)
        return verified

    return _sign_in


@pytest.fixture
def as_caller(monkeypatch):
    """Switch the current caller to an already-verified session."""

    def _as_caller(access_token):
        monkeypatch.setattr(session, 'get_access_token', lambda: access_token)

    return _as_caller


class FakeElicitationContext:
    """Stands in for get_context() during one round of a guard tool.

    A real Context exposes many more properties; a guard tool built so far only
    reads these two, so that is all this fakes.
    """

    def __init__(self, input_responses=None, request_state=None):
        self.input_responses = input_responses
        self.request_state = request_state


def acknowledged():
    """What a client sends back once the human has finished on a URL-mode
    elicitation's page - content carries nothing, since the whole point of
    URL mode is that no secret rides back through this channel."""
    return ElicitResult(action='accept', content=None)


@pytest.fixture
def elicit(monkeypatch):
    """Puts the next get_context() call's `.input_responses`/`.request_state` in
    place, the way FastMCP would for one round of a multi-round-trip tool call."""

    def _elicit(input_responses=None, request_state=None):
        context = FakeElicitationContext(input_responses, request_state)
        monkeypatch.setattr(session, 'get_context', lambda: context)
        return context

    return _elicit


class FakeRequestContext:
    def __init__(self, protocol_version):
        self.protocol_version = protocol_version


class FakeHandshakeEraSession:
    """Stands in for ctx.session during a handshake-era elicit_url() call.

    If `submit_values` is given, the fake submits the pending request itself as
    part of answering elicit_url - standing in for a page visit that happens to
    finish before the server's own poll loop first checks, which is the only
    case this test harness can exercise without a real sleep. Leave it None to
    exercise the "link never completed" (TTL-expiry) path instead.
    """

    def __init__(self, action='accept', submit_values=None):
        self.action = action
        self.submit_values = submit_values
        self.calls = []

    async def elicit_url(self, message, url, elicitation_id):
        self.calls.append({'message': message, 'url': url, 'elicitation_id': elicitation_id})
        if self.action == 'accept' and self.submit_values is not None:
            token = url.rsplit('/', 1)[-1]
            await secret_pages.get(token).submit(self.submit_values)
        return ElicitResult(action=self.action)


class FakeHandshakeEraContext:
    def __init__(self, session):
        self.session = session
        self.request_context = FakeRequestContext('2025-11-25')
        self.input_responses = None
        self.request_state = None


@pytest.fixture
def handshake_era(monkeypatch):
    """Puts a handshake-era get_context() in place, with a fake session whose
    elicit_url() records what it was asked and answers as configured."""

    def _handshake_era(action='accept', submit_values=None):
        fake_session = FakeHandshakeEraSession(action=action, submit_values=submit_values)
        monkeypatch.setattr(session, 'get_context', lambda: FakeHandshakeEraContext(fake_session))
        return fake_session

    return _handshake_era


@pytest.fixture
def drive_secret_tool(elicit):
    """Runs a URL-mode password-eliciting tool through both rounds a real
    session would.

    `call_tool` is a zero-argument callable invoking the tool with whatever
    non-secret arguments the test cares about already bound. Round 1 gets the
    `InputRequiredResult` and its token; `values` (a dict of field name -> value,
    or None to leave the page unsubmitted) is fed directly to the pending
    request's own `submit()` - standing in for a human filling out that page,
    the same way the real route handler would call it. Round 2 re-calls the
    tool with that token in `request_state` and returns whatever it resolves to.

    Returns `(asked, result)`: the `InputRequiredResult` from round 1, and
    round 2's outcome (the tool's real result, or another `InputRequiredResult`
    with the same link if `values` was None, since nobody finished the page).
    """

    async def _drive(call_tool, values):
        elicit()  # round 1: nothing asked yet
        asked = await call_tool()
        token = asked.request_state

        if values is not None:
            pending = secret_pages.get(token)
            assert pending is not None, 'no pending secret request was registered'
            await pending.submit(values)

        elicit({'secret': acknowledged()}, request_state=token)
        result = await call_tool()
        return asked, result

    return _drive
