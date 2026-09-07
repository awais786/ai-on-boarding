"""Elicitation (asking the human for a secret via a hosted page) and calling
Django with the caller's own, possibly-stale, credential.
"""

import asyncio
import os
import secrets

from fastmcp.server.dependencies import get_access_token, get_context
from mcp.types import ElicitRequest, ElicitRequestURLParams, InputRequiredResult
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

import credentials
import django_client
import secret_pages

MCP_BASE_URL = os.environ.get('MCP_BASE_URL', 'http://localhost:8100')

# Poll interval for a handshake-era call re-checking its page - see _await_secret.
HANDSHAKE_ERA_POLL_SECONDS = 1

SIGN_IN_AGAIN = 'Your session is no longer valid. Please sign in again.'  # never hints at a token
NEED_TO_SIGN_UP = 'No account found for this Google identity. Use the signup tool to create one.'


def _ask_for_secret(token, message):
    """Points the client at a page this server hosts, via URL-mode elicitation -
    not form mode, which the MCP spec forbids for secrets."""
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
    protocol where elicitation blocks on a direct call instead."""
    rc = getattr(ctx, 'request_context', None)
    if rc is None:
        return True
    return rc.protocol_version in MODERN_PROTOCOL_VERSIONS


async def _await_secret(fields, message, on_submit):
    """Collects one or more passwords via `secret_pages`, never a tool argument.
    `fields` is an ordered `[(name, label), ...]` list; `on_submit` does the real
    work once the human submits the page. Delegates to the handshake-era variant
    on an older protocol; otherwise this is a stateless multi-round-trip:
    register + ask, then re-check via `request_state` (the token FastMCP echoes
    back unmodified) until the page resolves."""
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
    if credentials.DJANGO_TOKEN_CLAIM not in get_access_token().claims:
        raise django_client.DjangoAPIError(NEED_TO_SIGN_UP)


async def _call_django(method, *args, access_token=None, **kwargs):
    """Call method(client, ...) - `method` an AuthedDjangoClient method, e.g.
    `django_client.AuthedDjangoClient.list_users` - refreshing a refused token
    once before giving up. Pass `access_token` explicitly when calling from
    outside a live MCP request (a secret page's `on_submit`); default is the
    current session's.

    The Django token lives inside the caller's signed JWT (see credentials.py),
    so a fresh one obtained here can't be written back into it - it only
    covers this one call.
    """
    if access_token is None:
        access_token = get_access_token()

    async def _attempt(django_token):
        client = django_client.AuthedDjangoClient(django_token)
        return await method(client, *args, **kwargs)

    try:
        return await _attempt(access_token.claims[credentials.DJANGO_TOKEN_CLAIM])
    except django_client.DjangoAPIError as err:
        if not err.stale_credential:
            raise

    try:
        google_token = access_token.claims[credentials.GOOGLE_TOKEN_CLAIM]
        django_token = await django_client.exchange_google_token(google_token)
    except django_client.DjangoAPIError:
        raise django_client.DjangoAPIError(SIGN_IN_AGAIN) from None

    try:
        return await _attempt(django_token)
    except django_client.DjangoAPIError as err:
        if not err.stale_credential:
            raise
        raise django_client.DjangoAPIError(SIGN_IN_AGAIN) from None
