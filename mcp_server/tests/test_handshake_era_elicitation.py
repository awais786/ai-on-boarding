"""Tests for the handshake-era branch of elicitation.py's await_secret.

A client that negotiates an MCP protocol version from 2024-11-05 through
2025-11-25 (e.g. today's MCP Inspector) has no multi-round-trip mechanism
(SEP-2322 exists only from 2026-07-28) - URL-mode elicitation there is instead
one blocking session.elicit_url() call, per the older wire shape. server.py
detects this via the negotiated protocol_version and polls the same
pending-request registry the modern path uses, within that one call, instead
of returning an InputRequiredResult for the client to round-trip.

handshake_era (conftest.py) fakes get_context() to report a handshake-era
protocol version and a session whose elicit_url() either submits the pending
request itself (simulating a page visit that finishes immediately) or leaves
it pending (simulating one that never completes, to exercise the TTL-expiry
path without a real wait).
"""

import pytest

import elicitation
import tools
from clients.base_client import BackendAPIError
from elicitation import ElicitationError

GOOGLE_A = 'google-token-a'


async def test_a_handshake_era_call_resolves_in_one_round(sign_in, django, handshake_era):
    await sign_in(GOOGLE_A)
    handshake_era(action='accept', submit_values={'new_password': 'new-password-1'})

    result = await tools.users.change_user_password('ada')

    assert result == {'detail': 'Password changed.'}


async def test_a_handshake_era_call_sends_exactly_one_elicit_url_request(
    sign_in, django, handshake_era
):
    await sign_in(GOOGLE_A)
    session = handshake_era(action='accept', submit_values={'new_password': 'new-password-1'})

    await tools.users.change_user_password('ada')

    assert len(session.calls) == 1
    assert session.calls[0]['url'].startswith(elicitation.MCP_BASE_URL)


async def test_declining_the_url_consent_cancels_without_registering_a_wait(
    sign_in, django, handshake_era
):
    await sign_in(GOOGLE_A)
    handshake_era(action='decline')

    result = await tools.users.change_user_password('ada')

    assert result == {'detail': 'Cancelled.'}
    assert django.calls == []


async def test_a_link_never_completed_is_reported_once_its_ttl_runs_out(
    sign_in, django, handshake_era, monkeypatch
):
    monkeypatch.setattr(elicitation, 'PENDING_TTL_SECONDS', -1)  # already expired by the time it's checked
    await sign_in(GOOGLE_A)
    handshake_era(action='accept', submit_values=None)  # never finishes the page

    with pytest.raises(ElicitationError) as failure:
        await tools.users.change_user_password('ada')

    assert 'try again' in str(failure.value).lower()
    assert django.calls == []


async def test_a_handshake_era_failure_is_reported_and_never_returns_the_password(
    sign_in, django, handshake_era
):
    await sign_in(GOOGLE_A)
    handshake_era(action='accept', submit_values={'new_password': 'weak'})

    with pytest.raises(BackendAPIError) as failure:
        await tools.users.change_user_password('ada')

    assert 'weak' not in str(failure.value)


async def test_a_handshake_era_token_is_retired_after_use(sign_in, django, handshake_era):
    await sign_in(GOOGLE_A)
    session = handshake_era(action='accept', submit_values={'new_password': 'new-password-1'})

    await tools.users.change_user_password('ada')

    token = session.calls[0]['url'].rsplit('/', 1)[-1]
    assert elicitation.get(token) is None


async def test_change_my_password_works_over_a_single_handshake_era_page(
    sign_in, django, handshake_era
):
    await sign_in(GOOGLE_A)
    handshake_era(
        action='accept',
        submit_values={'current_password': 'old-password-1', 'new_password': 'new-password-1'},
    )

    result = await tools.account.change_my_password()

    assert result == {'detail': 'Password changed.'}
