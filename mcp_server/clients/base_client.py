"""Shared transport plumbing every backend client uses: the one HTTP client
this server talks to the backend through, how to interpret a failed
response, and the authed-client base both account_client and users_client
build on.

Field allowlists live in each domain client (not the tools), so stripping
ids/emails happens once per domain. Username masking on reads lives in the
read tools themselves (tools/users/read.py), not here - this module's job is
talking to the backend, not deciding what a caller is allowed to see.
"""

import httpx2

from config import BACKEND_API_BASE, BACKEND_REQUEST_TIMEOUT

_client = httpx2.AsyncClient(base_url=BACKEND_API_BASE, timeout=BACKEND_REQUEST_TIMEOUT)

DETAIL_FALLBACK_MAX_LENGTH = 200  # bounds an unhandled backend error (can be a full HTML debug page)


class BackendAPIError(Exception):
    """A backend call did not succeed. Carries the backend's own detail message,
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


async def send_request(method, path, **kwargs):
    try:
        return await _client.request(method, path, **kwargs)
    except httpx2.RequestError as err:
        raise BackendAPIError('Could not reach the API.') from err


def raise_for_failure(response):
    if response.status_code == 401:
        raise BackendAPIError(extract_error_detail(response), stale_credential=True)
    if response.status_code != 200:
        raise BackendAPIError(extract_error_detail(response))


def extract_error_detail(response):
    """The backend's own `detail` message, or a length-capped fallback."""
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


class AuthedClient:
    """Shared instance state (the caller's own backend token) for every
    domain client that needs one - account_client.AccountClient and
    users_client.UsersClient. Each subclass exposes only the methods its own
    domain needs, so a tool that only imports one of them has no way to
    reach the other's operations through this base."""

    def __init__(self, backend_token):
        self.backend_token = backend_token

    def _headers(self):
        return {'Authorization': f'Token {self.backend_token}'}
