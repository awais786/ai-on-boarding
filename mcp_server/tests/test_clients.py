"""Tests for how the domain clients (clients/account_client.py,
clients/users_client.py) read Django's answers.

These go straight at the clients with a fake transport, because the 401-vs-403
distinction is what the whole recovery path turns on: a 401 means the credential
is stale and worth replacing, a 403 means Django answered correctly and replacing
the credential would only get the same refusal. The session-auth tests replace
the clients wholesale, so nothing there would notice this mapping inverting.
"""

import pytest

from clients import account_client, base_client, users_client


class FakeResponse:
    def __init__(self, status_code, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError('not json')
        return self._payload


class FakeClient:
    """Stands in for the shared httpx2.AsyncClient so send_request's own error
    handling really runs."""

    def __init__(self, raises=None, response=None):
        self._raises = raises
        self._response = response

    async def request(self, method, url, **kwargs):
        if self._raises is not None:
            raise self._raises
        return self._response


@pytest.fixture
def transport(monkeypatch):
    """Replace the shared HTTP client, leaving every line of base_client in play."""

    def _transport(raises=None, response=None):
        monkeypatch.setattr(base_client, '_client', FakeClient(raises, response))

    return _transport


@pytest.fixture
def responds(monkeypatch):
    """Make the next Django request return a given response, or raise."""

    def _responds(response=None, raises=None):
        async def _send(method, url, **kwargs):
            if raises is not None:
                raise raises
            return response

        monkeypatch.setattr(base_client, 'send_request', _send)

    return _responds


# --- 401 is a stale credential -----------------------------------------------


async def test_a_401_listing_users_is_a_credential_problem(responds):
    responds(FakeResponse(401, {'detail': 'Invalid token.'}))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await users_client.UsersClient('stale-token').list_users()

    assert failure.value.stale_credential


async def test_a_401_changing_a_password_is_a_credential_problem(responds):
    responds(FakeResponse(401, {'detail': 'Invalid token.'}))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await users_client.UsersClient('stale-token').change_password('ada', 'new-password-1')

    assert failure.value.stale_credential


async def test_a_401_exchanging_is_a_credential_problem(responds):
    responds(FakeResponse(401, {'detail': 'Google refused that token.'}))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await account_client.exchange_google_token('google-token-a')

    assert failure.value.stale_credential


# --- 403 is Django's real answer, not a stale credential ---------------------


async def test_a_403_changing_a_password_is_not_a_credential_problem(responds):
    responds(FakeResponse(403, {'detail': 'Only an admin may do that.'}))

    with pytest.raises(base_client.BackendAPIError) as refusal:
        await users_client.UsersClient('good-token').change_password('ada', 'new-password-1')

    assert not refusal.value.stale_credential
    assert str(refusal.value) == 'Only an admin may do that.'


async def test_a_403_listing_users_is_not_a_credential_problem(responds):
    responds(FakeResponse(403, {'detail': 'Not permitted.'}))

    with pytest.raises(base_client.BackendAPIError) as refusal:
        await users_client.UsersClient('good-token').list_users()

    assert not refusal.value.stale_credential


async def test_a_403_exchanging_means_no_account_here_not_a_stale_credential(responds):
    # /api/auth/google/ answers 403 when Google verified the person but this
    # project has no account it will sign in - same body for "no account" and
    # "embargoed", so this can't and doesn't try to tell them apart. Exchanging
    # again cannot help, so it must not be reported as a retryable credential
    # failure at the tool layer, but it also isn't Google itself refusing the
    # token - no_account is set so BackendGoogleProvider can admit the caller with
    # no credential instead of refusing them outright.
    responds(FakeResponse(403, {'detail': 'No account here.'}))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await account_client.exchange_google_token('google-token-a')

    assert failure.value.no_account
    assert not failure.value.stale_credential


async def test_a_401_exchanging_is_not_a_no_account_error(responds):
    responds(FakeResponse(401, {'detail': 'Google refused that token.'}))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await account_client.exchange_google_token('google-token-a')

    assert not failure.value.no_account


# --- Other failures ----------------------------------------------------------


async def test_a_500_is_an_ordinary_failure(responds):
    responds(FakeResponse(500, None, text='Server Error'))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await users_client.UsersClient('good-token').list_users()

    assert not failure.value.stale_credential


async def test_an_unreachable_django_is_reported_not_raised_raw(transport):
    import httpx2

    transport(raises=httpx2.ConnectError('connection refused'))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await users_client.UsersClient('good-token').list_users()

    assert 'reach' in str(failure.value).lower()


async def test_an_unreachable_django_during_an_exchange_is_reported(transport):
    import httpx2

    transport(raises=httpx2.ConnectError('connection refused'))

    with pytest.raises(base_client.BackendAPIError):
        await account_client.exchange_google_token('google-token-a')


async def test_a_timeout_is_reported_not_raised_raw(transport):
    import httpx2

    transport(raises=httpx2.ReadTimeout('too slow'))

    with pytest.raises(base_client.BackendAPIError):
        await users_client.UsersClient('good-token').list_users()


async def test_a_tool_result_field_allowlist_strips_ids_and_emails(responds):
    responds(
        FakeResponse(
            200,
            [
                {
                    'id': 7,
                    'username': 'ada',
                    'email': 'ada@example.com',
                    'country': 'GB',
                    'date_joined': '2026-01-01',
                }
            ],
        )
    )

    rows = await users_client.UsersClient('good-token').list_users()

    # The real username passes through here unmasked - masking it is a
    # read-tool concern (see test_users.py), not this client's.
    assert rows == [{'username': 'ada', 'country': 'GB', 'date_joined': '2026-01-01'}]


# --- _detail truncates a non-JSON fallback ------------------------------------


async def test_detail_returns_a_short_non_json_body_unchanged(responds):
    responds(FakeResponse(500, None, text='Server Error'))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await users_client.UsersClient('good-token').list_users()

    assert str(failure.value) == 'Server Error'


async def test_detail_truncates_a_long_non_json_body(responds):
    huge_debug_page = '<html>' + ('x' * 5000) + '</html>'
    responds(FakeResponse(500, None, text=huge_debug_page))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await users_client.UsersClient('good-token').list_users()

    message = str(failure.value)
    assert len(message) <= base_client.DETAIL_FALLBACK_MAX_LENGTH + len('...')
    assert message.endswith('...')
    assert message != huge_debug_page


async def test_detail_still_returns_a_json_detail_message_in_full(responds):
    # A real 'detail' field, however long, is not the thing being truncated - only
    # the non-JSON fallback is.
    long_detail = 'A' * 500
    responds(FakeResponse(403, {'detail': long_detail}))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await users_client.UsersClient('good-token').list_users()

    assert str(failure.value) == long_detail


# --- change_password refuses when no user matches ----------------------------


async def test_change_password_rejects_no_match(responds):
    responds(FakeResponse(404, {'detail': 'No user with that username.'}))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await users_client.UsersClient('good-token').change_password('nobody', 'new-password-1')

    assert not failure.value.stale_credential


# --- signup --------------------------------------------------------------------


async def test_signup_succeeds(responds):
    responds(FakeResponse(200, {'email': 'ada@example.com', 'username': 'ada'}))

    result = await account_client.signup('ada@example.com', 'ada', 'lovelace1', 'GB')

    assert result == {'detail': 'Account created.'}


async def test_signup_rejects_a_duplicate_email(responds):
    responds(FakeResponse(400, {'email': ['An account with this email already exists.']}))

    with pytest.raises(base_client.BackendAPIError):
        await account_client.signup('ada@example.com', 'ada', 'lovelace1', 'GB')


async def test_signup_never_returns_the_password(responds):
    responds(FakeResponse(200, {'email': 'ada@example.com', 'username': 'ada'}))

    result = await account_client.signup('ada@example.com', 'ada', 'lovelace1', 'GB')

    assert 'lovelace1' not in str(result)


# --- request_password_reset -----------------------------------------------------


async def test_request_password_reset_returns_djangos_response_unchanged(responds):
    body = {'detail': 'If that email address has an account, a reset link has been sent to it.'}
    responds(FakeResponse(200, body))

    result = await account_client.request_password_reset('ada@example.com')

    assert result == body


async def test_request_password_reset_reports_a_non_200(responds):
    responds(FakeResponse(429, {'detail': 'Too many reset requests for that address.'}))

    with pytest.raises(base_client.BackendAPIError):
        await account_client.request_password_reset('ada@example.com')


# --- confirm_password_reset ------------------------------------------------------


async def test_confirm_password_reset_succeeds(responds):
    responds(FakeResponse(200, {'detail': 'Your password has been changed.'}))

    result = await account_client.confirm_password_reset('a-code', 'new-password-1')

    assert result == {'detail': 'Password changed.'}


async def test_confirm_password_reset_rejects_an_invalid_code(responds):
    responds(FakeResponse(400, {'detail': 'That reset link is not valid.'}))

    with pytest.raises(base_client.BackendAPIError):
        await account_client.confirm_password_reset('bad-code', 'new-password-1')


async def test_confirm_password_reset_never_returns_the_new_password(responds):
    responds(FakeResponse(200, {'detail': 'Your password has been changed.'}))

    result = await account_client.confirm_password_reset('a-code', 'new-password-1')

    assert 'new-password-1' not in str(result)


# --- change_own_password ---------------------------------------------------------


async def test_change_own_password_succeeds(responds):
    responds(FakeResponse(200, {'detail': 'Password changed.'}))

    result = await account_client.AccountClient('good-token').change_own_password(
        'old-password-1', 'new-password-1'
    )

    assert result == {'detail': 'Password changed.'}


async def test_change_own_password_401_is_a_credential_problem(responds):
    responds(FakeResponse(401, {'detail': 'Invalid token.'}))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await account_client.AccountClient('stale-token').change_own_password(
            'old-password-1', 'new-password-1'
        )

    assert failure.value.stale_credential


async def test_change_own_password_rejects_a_wrong_current_password(responds):
    responds(FakeResponse(400, {'detail': 'Current password is incorrect.'}))

    with pytest.raises(base_client.BackendAPIError) as failure:
        await account_client.AccountClient('good-token').change_own_password(
            'wrong-password', 'new-password-1'
        )

    assert not failure.value.stale_credential
