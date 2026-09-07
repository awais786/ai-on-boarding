"""Tests for secret_pages.py and server.py's /secrets/{token} route.

Nothing in test_auth_tools.py or test_session_auth.py exercises this route for
real - drive_secret_tool (conftest.py) calls a pending request's submit()
directly, standing in for a human filling out the page without a real HTTP
request. These tests go the other way: a real Starlette TestClient against the
actual ASGI app, hitting the same route a browser would.
"""

import time

import pytest
from starlette.testclient import TestClient

import secret_pages
import server


@pytest.fixture
def client():
    return TestClient(server.mcp.http_app())


async def _noop(values):
    return {'detail': 'ok', **values}


# --- The registry itself --------------------------------------------------------


def test_register_returns_a_usable_token():
    token = secret_pages.register([('password', 'Password')], _noop)

    assert secret_pages.get(token) is not None


def test_get_of_an_unknown_token_is_none():
    assert secret_pages.get('never-registered') is None


def test_discard_removes_a_pending_request():
    token = secret_pages.register([('password', 'Password')], _noop)
    secret_pages.discard(token)

    assert secret_pages.get(token) is None


def test_an_expired_request_is_gone(monkeypatch):
    token = secret_pages.register([('password', 'Password')], _noop)
    real_pending = secret_pages._pending[token]
    monkeypatch.setattr(
        real_pending, 'created_at', time.monotonic() - secret_pages.PENDING_TTL_SECONDS - 1
    )

    assert secret_pages.get(token) is None


async def test_submit_runs_on_submit_and_stores_the_result():
    async def _create(values):
        return {'detail': 'created', 'username': values['username']}

    token = secret_pages.register([('username', 'Username')], _create)
    pending = secret_pages.get(token)

    await pending.submit({'username': 'ada'})

    assert pending.is_resolved
    assert pending.result == {'detail': 'created', 'username': 'ada'}
    assert pending.error is None


async def test_submit_stores_an_error_instead_of_raising():
    async def _fail(values):
        raise ValueError('nope')

    token = secret_pages.register([('password', 'Password')], _fail)
    pending = secret_pages.get(token)

    await pending.submit({'password': 'whatever'})  # must not raise

    assert pending.is_resolved
    assert pending.error == 'nope'
    assert pending.result is None


# --- The real HTTP route ---------------------------------------------------------


def test_get_an_unknown_token_is_404(client):
    response = client.get('/secrets/does-not-exist')

    assert response.status_code == 404
    assert 'expired' in response.text.lower()


def test_get_a_pending_tokens_page_renders_its_fields(client):
    token = secret_pages.register([('new_password', 'New password')], _noop)

    response = client.get(f'/secrets/{token}')

    assert response.status_code == 200
    assert 'New password' in response.text
    assert 'type="password"' in response.text


def test_posting_a_complete_form_resolves_the_pending_request(client):
    calls = []

    async def _on_submit(values):
        calls.append(values)
        return {'detail': 'Password changed.'}

    token = secret_pages.register([('new_password', 'New password')], _on_submit)

    response = client.post(f'/secrets/{token}', data={'new_password': 'lovelace1'})

    assert response.status_code == 200
    assert 'Done' in response.text
    assert calls == [{'new_password': 'lovelace1'}]
    assert secret_pages.get(token).result == {'detail': 'Password changed.'}


def test_posting_with_a_missing_field_reprompts_without_resolving(client):
    token = secret_pages.register([('new_password', 'New password')], _noop)

    response = client.post(f'/secrets/{token}', data={})

    assert response.status_code == 400
    assert 'required' in response.text.lower()
    assert not secret_pages.get(token).is_resolved


def test_posting_a_failing_submission_shows_the_error_and_resolves_it(client):
    async def _reject(values):
        raise ValueError('Current password is incorrect.')

    token = secret_pages.register([('current_password', 'Current password')], _reject)

    response = client.post(f'/secrets/{token}', data={'current_password': 'wrong'})

    assert response.status_code == 400
    assert 'Current password is incorrect.' in response.text
    assert secret_pages.get(token).is_resolved


def test_a_resolved_tokens_page_is_gone_on_a_second_visit(client):
    token = secret_pages.register([('password', 'Password')], _noop)
    client.post(f'/secrets/{token}', data={'password': 'lovelace1'})

    response = client.get(f'/secrets/{token}')

    assert response.status_code == 404


def test_the_password_submitted_is_not_echoed_back_in_the_response(client):
    token = secret_pages.register([('password', 'Password')], _noop)

    response = client.post(f'/secrets/{token}', data={'password': 'a-secret-value-1'})

    assert 'a-secret-value-1' not in response.text


def test_a_message_containing_html_is_escaped_not_injected(client):
    token = secret_pages.register(
        [('password', '<script>alert(1)</script>')], _noop
    )

    response = client.get(f'/secrets/{token}')

    assert '<script>alert(1)</script>' not in response.text
    assert '&lt;script&gt;' in response.text
