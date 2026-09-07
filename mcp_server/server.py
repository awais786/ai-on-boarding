"""MCP server exposing signup-reporting tools backed by the Django API.

Google authenticates a caller once; the first request of a session trades that
for this project's own Django token, reused for later requests. Tools call
Django with the caller's own token, not a blanket service credential.
"""

import asyncio
import hashlib
import os
import secrets
import time

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token, get_context
from mcp.types import ElicitRequest, ElicitRequestURLParams, InputRequiredResult
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from starlette.responses import HTMLResponse

import django_client
import secret_pages
from mcp_middleware import ToolCallLogger, ToolCallRateLimiter

load_dotenv()

MCP_BASE_URL = os.environ.get('MCP_BASE_URL', 'http://localhost:8100')

# Poll interval for a handshake-era call re-checking its page - see _await_secret.
HANDSHAKE_ERA_POLL_SECONDS = 1

# A ceiling only: a revoked Google token expires the cache entry sooner regardless.
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


def _ask_for_secret(token, message):
    """Points the client at a page this server hosts, via URL-mode elicitation -
    not form mode, which the MCP spec forbids for secrets (it stays inside the
    client, with nothing stopping it reaching the model too)."""
    return InputRequiredResult(
        input_requests={
            'secret': ElicitRequest(
                method='elicitation/create',
                params=ElicitRequestURLParams(
                    mode='url',
                    message=message,
                    url=f'{MCP_BASE_URL}/secrets/{token}',
                ),
            )
        },
        request_state=token,
    )


def _is_modern_protocol(ctx):
    """2026-07-28 (multi-round-trip, SEP-2322) vs an earlier "handshake-era"
    protocol, where elicitation blocks on a direct call instead. Defaults to
    modern when the era can't be read from the context."""
    rc = getattr(ctx, 'request_context', None)
    if rc is None:
        return True
    return rc.protocol_version in MODERN_PROTOCOL_VERSIONS


async def _await_secret(fields, message, on_submit):
    """Collects one or more passwords via `secret_pages`, never a tool argument.
    `fields` is an ordered `[(name, label), ...]` list; `on_submit` does the real
    work once the human submits the page. Delegates to the handshake-era variant
    below on an older protocol (see _is_modern_protocol); otherwise this is a
    stateless multi-round-trip: register + ask, then re-check via `request_state`
    (the token FastMCP echoes back unmodified) until the page resolves."""
    ctx = get_context()

    if not _is_modern_protocol(ctx):
        return await _await_secret_handshake_era(ctx, fields, message, on_submit)

    responses = ctx.input_responses

    if responses is None:
        token = secret_pages.register(fields, on_submit)
        return _ask_for_secret(token, message)

    token = ctx.request_state
    pending = secret_pages.get(token)
    if pending is None:
        return {'detail': 'That link expired before it was completed. Please try again.'}

    if not pending.is_resolved:
        return _ask_for_secret(token, message)  # still waiting on the human

    secret_pages.discard(token)
    if pending.error is not None:
        raise django_client.DjangoAPIError(pending.error)
    return pending.result


async def _await_secret_handshake_era(ctx, fields, message, on_submit):
    token = secret_pages.register(fields, on_submit)
    try:
        consent = await ctx.session.elicit_url(
            message=message,
            url=f'{MCP_BASE_URL}/secrets/{token}',
            elicitation_id=secrets.token_urlsafe(16),
        )
        if consent.action != 'accept':
            return {'detail': 'Cancelled.'}

        pending = secret_pages.get(token)
        while pending is not None and not pending.is_resolved:
            await asyncio.sleep(HANDSHAKE_ERA_POLL_SECONDS)
            pending = secret_pages.get(token)

        if pending is None:
            raise django_client.DjangoAPIError(
                'That link expired before it was completed. Please try again.'
            )
        if pending.error is not None:
            raise django_client.DjangoAPIError(pending.error)
        return pending.result
    finally:
        secret_pages.discard(token)


def _require_django_token():
    """Raise a clear refusal if the caller's session has no Django credential yet."""
    if DJANGO_TOKEN_CLAIM not in get_access_token().claims:
        raise django_client.DjangoAPIError(NEED_TO_SIGN_UP)


async def _call_django(django_call, *args, access_token=None, **kwargs):
    """Call django_call(django_token, ...), refreshing a refused token once before
    giving up. Pass `access_token` explicitly when calling from outside a live
    MCP request (a secret page's `on_submit`), where get_access_token() has
    nothing to read - default is the current session's."""
    if access_token is None:
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
async def change_user_password(username: str):
    """Change a user's password. Only works if the caller is an admin.

    The new password is collected on a page this server hosts, not a tool
    argument - never seen by your MCP client or this assistant.
    """
    _require_django_token()
    access_token = get_access_token()

    async def _do_change(values):
        django_client.validate_password_strength(values['new_password'])
        return await _call_django(
            django_client.change_password, username, values['new_password'], access_token=access_token
        )

    return await _await_secret(
        [('new_password', "New password")],
        f"Choose {username}'s new password.",
        _do_change,
    )


@mcp.tool()
async def signup(email: str, username: str, country: str):
    """Create an account. Works even if you don't have one yet - that's the point.

    The password is collected on a page this server hosts, not a tool argument -
    never seen by your MCP client or this assistant. On success, this session
    can immediately use the other tools without reconnecting.
    """
    access_token = get_access_token()

    async def _do_signup(values):
        django_client.validate_password_strength(values['password'])
        result = await django_client.signup(email, username, values['password'], country)

        try:
            django_token = await django_client.exchange_google_token(access_token.token)
        except django_client.DjangoAPIError:
            return result  # account exists; the next call resolves a credential the normal way

        _credentials.replace_django_token(access_token.token, django_token)
        return result

    return await _await_secret([('password', 'Password')], 'Choose a password.', _do_signup)


@mcp.tool()
async def request_password_reset(email: str):
    """Request a password-reset code by email. The reply is the same whether or not that
    address has an account - it never reveals who is signed up."""
    return await django_client.request_password_reset(email)


@mcp.tool()
async def reset_password(code: str):
    """Complete a password reset using the code emailed by request_password_reset.

    The new password is collected on a page this server hosts, not a tool
    argument - never seen by your MCP client or this assistant.
    """

    async def _do_reset(values):
        django_client.validate_password_strength(values['new_password'])
        return await django_client.confirm_password_reset(code, values['new_password'])

    return await _await_secret([('new_password', 'New password')], 'Choose a new password.', _do_reset)


@mcp.tool()
async def change_my_password():
    """Change your own password. Requires an account - use signup first if you don't have one.

    Both passwords are collected on a page this server hosts, not tool
    arguments - never seen by your MCP client or this assistant.
    """
    _require_django_token()
    access_token = get_access_token()

    async def _do_change(values):
        django_client.validate_password_strength(values['new_password'])
        return await _call_django(
            django_client.change_own_password,
            values['current_password'],
            values['new_password'],
            access_token=access_token,
        )

    return await _await_secret(
        [('current_password', 'Current password'), ('new_password', 'New password')],
        'Enter your current password and choose a new one.',
        _do_change,
    )


@mcp.custom_route('/secrets/{token}', methods=['GET', 'POST'])
async def secret_page(request):
    """The page every `_await_secret` URL points at. Not part of the MCP
    protocol - an ordinary HTTP route a browser loads directly, per SEP-1036.
    """
    token = request.path_params['token']
    pending = secret_pages.get(token)
    if pending is None or pending.is_resolved:
        return HTMLResponse(secret_pages.render_gone(), status_code=404)

    if request.method == 'GET':
        return HTMLResponse(secret_pages.render_form(token, pending.fields))

    form = await request.form()
    values = {name: form.get(name, '') for name, _ in pending.fields}
    missing = [label for name, label in pending.fields if not values.get(name)]
    if missing:
        return HTMLResponse(
            secret_pages.render_form(token, pending.fields, error=f"{', '.join(missing)} required."),
            status_code=400,
        )

    await pending.submit(values)
    if pending.error is not None:
        return HTMLResponse(secret_pages.render_error(pending.error), status_code=400)
    return HTMLResponse(secret_pages.render_done())


if __name__ == '__main__':
    mcp.run(transport='http', host='0.0.0.0', port=8100)
