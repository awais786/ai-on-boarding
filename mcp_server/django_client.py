"""The only place this server talks to the Django API.

Field allowlists live here, not in the tools, so stripping ids/emails happens
once. Password strength isn't checked here either - each tool's own
secret_pages on_submit closure (server.py) does that.
"""

import os
import re

import httpx2

DJANGO_API_BASE = os.environ.get('DJANGO_API_BASE', 'http://localhost:8000/api')
REQUEST_TIMEOUT = 10

GOOGLE_AUTH_PATH = '/auth/google/'
USERS_PATH = '/users/'
SELF_CHANGE_PASSWORD_PATH = '/users/me/change-password/'
SIGNUP_PATH = '/signup/'
PASSWORD_RESET_PATH = '/password-reset/'
PASSWORD_RESET_CONFIRM_PATH = '/password-reset/confirm/'


def _admin_change_password_path(username):
    return f'{USERS_PATH}{username}/change-password/'


# Mirrors sdd_django_demo/api/serializers.py::validate_password_strength - both
# run password_strength_cases.json so a drift between them fails a test.
PASSWORD_MIN_LENGTH = 8

django_client = httpx2.AsyncClient(base_url=DJANGO_API_BASE, timeout=REQUEST_TIMEOUT)

USER_FIELDS = ('username', 'country', 'date_joined')  # id/email deliberately excluded - PII the tools don't need
MASKED_USERNAME = '***'  # real on the way in, masked on the way out - see list_users
DETAIL_FALLBACK_MAX_LENGTH = 200  # bounds an unhandled Django error (can be a full HTML debug page)


class DjangoAPIError(Exception):
    """A Django call did not succeed. Carries the server's own detail message,
    plus two flags callers branch on instead of a type hierarchy:

    `stale_credential` - the token itself was refused (401); worth retrying
    with a fresh one.

    `no_account` - only exchange_google_token sets this (403 there): Google
    recognises the caller but no account matches, so the caller is let
    through with no credential instead of refused outright, keeping signup
    reachable.
    """

    def __init__(self, detail, *, stale_credential=False, no_account=False):
        super().__init__(detail)
        self.stale_credential = stale_credential
        self.no_account = no_account


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
    if response.status_code == 401:
        raise DjangoAPIError(extract_error_detail(response), stale_credential=True)
    if response.status_code != 200:
        raise DjangoAPIError(extract_error_detail(response))


async def exchange_google_token(google_access_token):
    """Trade a verified Google access token for this project's own DRF token."""
    response = await send_request(
        'POST', GOOGLE_AUTH_PATH, json={'access_token': google_access_token}
    )

    if response.status_code == 401:
        raise DjangoAPIError(extract_error_detail(response), stale_credential=True)
    if response.status_code == 403:
        raise DjangoAPIError(extract_error_detail(response), no_account=True)
    if response.status_code != 200:
        raise DjangoAPIError(extract_error_detail(response))

    return response.json()['token']


async def signup(email, username, password, country):
    """Create an account. No credential is sent - a caller with none is exactly who calls this."""
    response = await send_request(
        'POST',
        SIGNUP_PATH,
        json={'email': email, 'username': username, 'password': password, 'country': country},
    )
    _raise_for_failure(response)
    return {'detail': 'Account created.'}


async def request_password_reset(email):
    """Ask Django to email a reset code. The response is identical whether or not the
    address has an account - returned as-is, so that stays true here too."""
    response = await send_request('POST', PASSWORD_RESET_PATH, json={'email': email})
    _raise_for_failure(response)
    return response.json()


async def confirm_password_reset(code, new_password):
    """Spend a reset code and set the new password."""
    response = await send_request(
        'POST', PASSWORD_RESET_CONFIRM_PATH, json={'code': code, 'password': new_password}
    )
    _raise_for_failure(response)
    return {'detail': 'Password changed.'}


class AuthedDjangoClient:
    """Calls that need the caller's own Django token, held as instance state
    instead of a leading parameter on every function. Calls needing no
    credential (signup, request_password_reset, confirm_password_reset,
    exchange_google_token) stay module functions."""

    def __init__(self, django_token):
        self.django_token = django_token

    def _headers(self):
        return {'Authorization': f'Token {self.django_token}'}

    async def _get_users(self, country=None, username=None):
        """The raw, unfiltered rows - id included. Internal use only."""
        params = {}
        if country:
            params['country'] = country
        if username:
            params['username'] = username

        response = await send_request('GET', USERS_PATH, params=params, headers=self._headers())
        _raise_for_failure(response)
        return response.json()

    async def list_users(self, country=None):
        """Signup users, optionally filtered by country. Stripped to USER_FIELDS,
        with the real username replaced by MASKED_USERNAME in every row."""
        rows = await self._get_users(country=country)
        return [
            {field: (MASKED_USERNAME if field == 'username' else row[field]) for field in USER_FIELDS}
            for row in rows
        ]

    async def change_password(self, username, new_password):
        response = await send_request(
            'POST',
            _admin_change_password_path(username),
            json={'password': new_password},
            headers=self._headers(),
        )
        _raise_for_failure(response)
        return {'detail': 'Password changed.'}

    async def change_own_password(self, current_password, new_password):
        response = await send_request(
            'POST',
            SELF_CHANGE_PASSWORD_PATH,
            json={'current_password': current_password, 'new_password': new_password},
            headers=self._headers(),
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
