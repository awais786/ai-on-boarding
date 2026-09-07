"""The only place this server talks to the Django API.

Field allowlists live here, not in the tools: whatever a tool returns is what the
LLM sees, so stripping ids, emails, etc. happens once, here, rather than being
left to every tool author to remember. Password strength isn't checked here
either - each tool's own secret_pages on_submit closure (server.py) does that.
"""

import os
import re

import httpx2

DJANGO_API_BASE = os.environ.get('DJANGO_API_BASE', 'http://localhost:8000/api')
REQUEST_TIMEOUT = 10

# Mirrors sdd_django_demo/api/serializers.py::validate_password_strength - both
# run password_strength_cases.json so a drift between them fails a test.
PASSWORD_MIN_LENGTH = 8

django_client = httpx2.AsyncClient(base_url=DJANGO_API_BASE, timeout=REQUEST_TIMEOUT)

# id and email are deliberately left out - internal identifiers and PII the tools don't need.
USER_FIELDS = ('username', 'country', 'date_joined')

# Real on the way in, masked on the way out (see list_users) - a listing shows who
# signed up from where, not any exact username.
MASKED_USERNAME = '***'

# Bounds the fallback used when Django doesn't send a JSON `detail` - an unhandled
# Django error can be a full HTML debug page, which has no business in an LLM's context.
DETAIL_FALLBACK_MAX_LENGTH = 200


class DjangoAPIError(Exception):
    """A Django call did not succeed. Carries the server's own detail message."""


class DjangoAuthError(DjangoAPIError):
    """The credential is stale - worth retrying with a fresh one. Kept apart from
    a plain 403 (non-admin, embargoed, ...), which is Django answering correctly
    and would just refuse again on retry."""


class NoDjangoAccountError(DjangoAuthError):
    """Google recognises the caller, but no account (or an embargoed one) matches -
    the identity is fine, so this lets the session through with no credential
    instead of refusing outright, so signup is still reachable."""


def validate_password_strength(password):
    """Reject a password Django would reject too, before spending a round trip on it."""
    if (
        len(password) < PASSWORD_MIN_LENGTH
        or not re.search(r'[A-Za-z]', password)
        or not re.search(r'\d', password)
    ):
        raise DjangoAPIError(
            f'Must be at least {PASSWORD_MIN_LENGTH} characters and contain a letter and a digit.'
        )


async def send_request(method, path, **kwargs):
    try:
        return await django_client.request(method, path, **kwargs)
    except httpx2.RequestError as err:
        raise DjangoAPIError('Could not reach the API.') from err


def _raise_for_failure(response):
    """401 -> stale credential; other non-200 -> ordinary failure. Not used by
    exchange_google_token, which also handles a 403 (NoDjangoAccountError)."""
    if response.status_code == 401:
        raise DjangoAuthError(extract_error_detail(response))
    if response.status_code != 200:
        raise DjangoAPIError(extract_error_detail(response))


async def exchange_google_token(google_access_token):
    """Trade a verified Google access token for this project's own DRF token."""
    response = await send_request(
        'POST', '/auth/google/', json={'access_token': google_access_token}
    )

    # 401: Google refused the token. 403: no account for this identity - kept
    # distinct so the caller can still be let through to sign up.
    if response.status_code == 401:
        raise DjangoAuthError(extract_error_detail(response))
    if response.status_code == 403:
        raise NoDjangoAccountError(extract_error_detail(response))
    if response.status_code != 200:
        raise DjangoAPIError(extract_error_detail(response))

    return response.json()['token']


async def _get_users(django_token, country=None, username=None):
    """The raw, unfiltered rows - id included. Internal use only; never returned
    directly from a tool."""
    params = {}
    if country:
        params['country'] = country
    if username:
        params['username'] = username

    response = await send_request(
        'GET', '/users/', params=params, headers={'Authorization': f'Token {django_token}'}
    )
    _raise_for_failure(response)
    return response.json()


async def list_users(django_token, country=None):
    """Signup users, optionally filtered by country. Stripped to USER_FIELDS, with
    the real username replaced by MASKED_USERNAME in every row."""
    rows = await _get_users(django_token, country=country)
    return [
        {field: (MASKED_USERNAME if field == 'username' else row[field]) for field in USER_FIELDS}
        for row in rows
    ]


async def change_password(django_token, username, new_password):
    """Set a user's password by username, so no internal id ever reaches the LLM."""
    response = await send_request(
        'POST',
        f'/users/{username}/change-password/',
        json={'password': new_password},
        headers={'Authorization': f'Token {django_token}'},
    )
    _raise_for_failure(response)
    return {'detail': 'Password changed.'}


async def signup(email, username, password, country):
    """Create an account. No credential is sent - a caller with none is exactly who calls this."""
    response = await send_request(
        'POST',
        '/signup/',
        json={'email': email, 'username': username, 'password': password, 'country': country},
    )
    _raise_for_failure(response)
    return {'detail': 'Account created.'}


async def request_password_reset(email):
    """Ask Django to email a reset code. The response is identical whether or not the
    address has an account - returned as-is, so that stays true here too."""
    response = await send_request('POST', '/password-reset/', json={'email': email})
    _raise_for_failure(response)
    return response.json()


async def confirm_password_reset(code, new_password):
    """Spend a reset code and set the new password."""
    response = await send_request(
        'POST', '/password-reset/confirm/', json={'code': code, 'password': new_password}
    )
    _raise_for_failure(response)
    return {'detail': 'Password changed.'}


async def change_own_password(django_token, current_password, new_password):
    """Change the caller's own password, current password verified by Django first."""
    response = await send_request(
        'POST',
        '/users/me/change-password/',
        json={'current_password': current_password, 'new_password': new_password},
        headers={'Authorization': f'Token {django_token}'},
    )
    _raise_for_failure(response)
    return {'detail': 'Password changed.'}


def extract_error_detail(response):
    """Django's own `detail` message, or a length-capped fallback."""
    try:
        payload = response.json()
    except ValueError:
        return truncate_text(response.text)

    if isinstance(payload, dict) and 'detail' in payload:
        return payload['detail']
    return truncate_text(response.text)


def truncate_text(text):
    if len(text) > DETAIL_FALLBACK_MAX_LENGTH:
        return text[:DETAIL_FALLBACK_MAX_LENGTH] + '...'
    return text
