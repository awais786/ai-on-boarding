"""MCP server exposing signup-reporting tools backed by the Django API.

Google authenticates a caller once; FastMCP keeps the Google token server-side and
the first request of a session trades it for this project's own Django token, which
later requests reuse. Tools call Django with the caller's own token, so Django's own
permission checks apply to the real caller, not a blanket service credential.
"""

import hashlib
import json
import os
import time

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token, get_context
from mcp.types import ElicitRequest, ElicitRequestFormParams, InputRequiredResult

import django_client
from mcp_middleware import PasswordStrengthMiddleware, ToolCallLogger, ToolCallRateLimiter

load_dotenv()

MCP_BASE_URL = os.environ.get('MCP_BASE_URL', 'http://localhost:8100')

# A revoked Google token still expires the cache entry sooner than this, so raising
# this value never extends a revoked account's life.
CREDENTIAL_CACHE_TTL_SECONDS = int(os.environ.get('MCP_CREDENTIAL_CACHE_TTL_SECONDS', '86400'))
CREDENTIAL_CACHE_MAX_SIZE = 1_000
CREDENTIAL_CACHE_FALLBACK_TTL_SECONDS = 3600  # used if a token carries no expiry of its own
CACHE_CLEANUP_INTERVAL_SECONDS = 60

GOOGLE_CLAIMS_TO_KEEP = ('sub', 'email')  # the rest (name, picture, ...) is unused
SIGN_IN_AGAIN = 'Your session is no longer valid. Please sign in again.'  # never hints at a token
NEED_TO_SIGN_UP = 'No account found for this Google identity. Use the signup tool to create one.'
DJANGO_TOKEN_CLAIM = 'django_token'  # where the Django token rides on a tool's AccessToken

auth = GoogleProvider(
    client_id=os.environ['GOOGLE_CLIENT_ID'],
    client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
    base_url=MCP_BASE_URL,
    required_scopes=['openid', 'email'],
)


class CredentialCache:
    """Verified identity and Django token for a caller, keyed by a hash of their Google token.

    Unlike FastMCP's own TokenCache, entries can be replaced - needed to recover
    from a Django token Django stops accepting without re-exchanging on every call.
    """

    def __init__(self, ttl_seconds, max_size=CREDENTIAL_CACHE_MAX_SIZE):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._entries = {}
        self._last_cleanup = time.monotonic()

    def get(self, google_token):
        key = self._key(google_token)
        entry = self._entries.get(key)
        if entry is None:
            return None
        access_token, expires_at = entry
        if expires_at < time.time():
            del self._entries[key]
            return None
        return access_token.model_copy(deep=True)

    def set(self, google_token, access_token):
        """Cache a verified, exchanged AccessToken. Only ever call this on success."""
        key = self._key(google_token)
        self._maybe_cleanup()
        if key not in self._entries:
            self._enforce_size_limit()

        token_expires_at = (
            float(access_token.expires_at)
            if access_token.expires_at
            else time.time() + CREDENTIAL_CACHE_FALLBACK_TTL_SECONDS
        )
        expires_at = min(time.time() + self._ttl, token_expires_at)
        self._entries[key] = (access_token.model_copy(deep=True), expires_at)

    def discard(self, google_token):
        """Forget a session, so a refused credential can't stay cached and wedge it."""
        self._entries.pop(self._key(google_token), None)

    def replace_django_token(self, google_token, django_token):
        """Point an existing entry at a freshly exchanged Django token; a no-op if evicted."""
        key = self._key(google_token)
        entry = self._entries.get(key)
        if entry is None:
            return
        access_token, expires_at = entry
        replacement = access_token.model_copy(deep=True)
        replacement.claims[DJANGO_TOKEN_CLAIM] = django_token
        self._entries[key] = (replacement, expires_at)

    @staticmethod
    def _key(token):
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    def _cleanup_expired(self):
        now = time.time()
        for key in [k for k, (_, expires_at) in self._entries.items() if expires_at < now]:
            del self._entries[key]

    def _maybe_cleanup(self):
        now = time.monotonic()
        if now - self._last_cleanup > CACHE_CLEANUP_INTERVAL_SECONDS:
            self._cleanup_expired()
            self._last_cleanup = now

    def _enforce_size_limit(self):
        if len(self._entries) < self._max_size:
            return
        self._cleanup_expired()
        if len(self._entries) >= self._max_size:
            del self._entries[next(iter(self._entries))]


class CredentialVerifier:
    """Wraps GoogleProvider's own verifier to also exchange the token for a Django one."""

    def __init__(self, inner_verifier, cache):
        self._inner = inner_verifier
        self._cache = cache

    async def verify_token(self, token):
        cached = self._cache.get(token)
        if cached is not None:
            return cached

        verified = await self._inner.verify_token(token)
        if verified is None:
            return None

        verified.claims = {
            key: value for key, value in verified.claims.items() if key in GOOGLE_CLAIMS_TO_KEEP
        }

        try:
            verified.claims[DJANGO_TOKEN_CLAIM] = await django_client.exchange_google_token(token)
        except django_client.NoDjangoAccountError:
            pass  # identity is fine, no account yet - admit the session with no credential
        except django_client.DjangoAPIError:
            return None  # Google itself refused the token, or Django is unreachable

        self._cache.set(token, verified)
        return verified


_credentials = CredentialCache(ttl_seconds=CREDENTIAL_CACHE_TTL_SECONDS)
auth._token_validator = CredentialVerifier(auth._token_validator, _credentials)

mcp = FastMCP('django-user-reporting', auth=auth)

mcp.add_middleware(ToolCallLogger())  # outermost, so it also logs a rate-limit rejection
mcp.add_middleware(ToolCallRateLimiter())
mcp.add_middleware(PasswordStrengthMiddleware())  # innermost: still counts against the rate limit


def _ask_for_password(key, message, request_state=None):
    """An InputRequiredResult asking the caller's own MCP client - never the LLM -
    to collect one password-shaped field, keyed by `key`.

    Multi-round-trip is stateless (SEP-2322): nothing survives here between
    rounds except what rides in `request_state`, which FastMCP seals on the wire
    (encrypted with a server-held key) before handing it to the client, so a
    password carried forward in it is never plaintext outside this process.
    """
    return InputRequiredResult(
        input_requests={
            key: ElicitRequest(
                method='elicitation/create',
                params=ElicitRequestFormParams(
                    message=message,
                    requested_schema={
                        'type': 'object',
                        'properties': {key: {'type': 'string', 'format': 'password'}},
                        'required': [key],
                    },
                ),
            )
        },
        request_state=request_state,
    )


def _answered(responses, key):
    """The client's plain value for an elicited field, or None if it declined/cancelled -
    never raise on a decline, since "the caller changed their mind" isn't an error."""
    answer = responses.get(key)
    if answer is None or answer.action != 'accept':
        return None
    return answer.content[key]


def _require_django_token():
    """Raise a clear refusal if the caller's session has no Django credential yet."""
    if DJANGO_TOKEN_CLAIM not in get_access_token().claims:
        raise django_client.DjangoAPIError(NEED_TO_SIGN_UP)


async def _call_django(django_call, *args, **kwargs):
    """Call django_call(django_token, ...), refreshing a refused token once before giving up."""
    access_token = get_access_token()
    try:
        return await django_call(access_token.claims[DJANGO_TOKEN_CLAIM], *args, **kwargs)
    except django_client.DjangoAuthError:
        pass

    try:
        django_token = await django_client.exchange_google_token(access_token.token)
    except django_client.DjangoAPIError:
        _credentials.discard(access_token.token)
        raise django_client.DjangoAPIError(SIGN_IN_AGAIN) from None

    _credentials.replace_django_token(access_token.token, django_token)
    try:
        return await django_call(django_token, *args, **kwargs)
    except django_client.DjangoAuthError:
        _credentials.discard(access_token.token)
        raise django_client.DjangoAPIError(SIGN_IN_AGAIN) from None


@mcp.tool()
async def list_signup_users():
    """List every signed-up user (username, country, signup date). Admin only."""
    _require_django_token()
    return await _call_django(django_client.list_users)


@mcp.tool()
async def list_users_by_country(country: str):
    """List signed-up users from a specific country. Admin only."""
    _require_django_token()
    return await _call_django(django_client.list_users, country=country)


@mcp.tool()
async def change_user_password(username: str, new_password: str):
    """Change a user's password. Only works if the caller is an admin."""
    _require_django_token()
    return await _call_django(django_client.change_password, username, new_password)


@mcp.tool()
async def signup(email: str, username: str, password: str, country: str):
    """Create an account. Works even if you don't have one yet - that's the point.

    On success, this session can immediately use the other tools without reconnecting.
    """
    result = await django_client.signup(email, username, password, country)

    access_token = get_access_token()
    try:
        django_token = await django_client.exchange_google_token(access_token.token)
    except django_client.DjangoAPIError:
        return result  # account exists; the next call resolves a credential the normal way

    _credentials.replace_django_token(access_token.token, django_token)
    return result


@mcp.tool()
async def request_password_reset(email: str):
    """Request a password-reset code by email. The reply is the same whether or not that
    address has an account - it never reveals who is signed up."""
    return await django_client.request_password_reset(email)


@mcp.tool()
async def reset_password(code: str, new_password: str):
    """Complete a password reset using the code emailed by request_password_reset."""
    return await django_client.confirm_password_reset(code, new_password)


@mcp.tool()
async def change_my_password():
    """Change your own password. Requires an account - use signup first if you don't have one.

    Neither password is a parameter of this tool: your MCP client collects both
    directly from you, over two rounds, so the calling assistant never sees them.
    """
    _require_django_token()

    ctx = get_context()
    responses = ctx.input_responses

    if responses is None:
        return _ask_for_password('current_password', 'Enter your current password.')

    current_password = _answered(responses, 'current_password')
    if 'current_password' in responses and current_password is None:
        return {'detail': 'Password change cancelled.'}

    if current_password is not None:
        return _ask_for_password(
            'new_password',
            'Choose a new password (at least 8 characters, with a letter and a digit).',
            request_state=json.dumps({'current_password': current_password}),
        )

    new_password = _answered(responses, 'new_password')
    if new_password is None:
        return {'detail': 'Password change cancelled.'}

    django_client.validate_password_strength(new_password)
    current_password = json.loads(ctx.request_state)['current_password']
    return await _call_django(django_client.change_own_password, current_password, new_password)


if __name__ == '__main__':
    mcp.run(transport='http', host='0.0.0.0', port=8100)
