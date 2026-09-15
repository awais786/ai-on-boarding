"""Collecting a secret from the human directly, never through the MCP
protocol, client, or model: the hosted page itself (SEP-1036) and the
tool-side wait for it to be submitted, including the handshake-era fallback
for older MCP clients.

Not to be confused with auth.py, which calls the backend with the caller's
own credential once a secret has been collected - a related but separate
concern (see that module's own docstring).
"""

import asyncio
import html
import secrets
import time

from fastmcp.server.dependencies import get_context
from mcp.types import ElicitRequest, ElicitRequestURLParams, InputRequiredResult
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

from clients.base_client import BackendAPIError
from config import HANDSHAKE_ERA_POLL_SECONDS, MCP_BASE_URL
from config import SECRET_PAGE_TTL_SECONDS as PENDING_TTL_SECONDS

TOKEN_BYTES = 32


class PendingSecretRequest:
    """One outstanding "collect a password" request. `fields` is an ordered
    [(name, label), ...] list."""

    def __init__(self, fields, on_submit):
        self.fields = fields
        self._on_submit = on_submit
        self.created_at = time.monotonic()
        self.result = None
        self.error = None

    @property
    def is_expired(self):
        return time.monotonic() - self.created_at > PENDING_TTL_SECONDS

    @property
    def is_resolved(self):
        return self.result is not None or self.error is not None

    async def submit(self, values):
        """Runs the real operation. Only ever called from this module's own POST
        handler - values never leave this process."""
        try:
            self.result = await self._on_submit(values)
        except Exception as exc:  # noqa: BLE001 - surfaced to the waiting tool call
            self.error = str(exc)


_pending = {}


def register(fields, on_submit):
    """Register a pending request and return its one-time token."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    _pending[token] = PendingSecretRequest(fields, on_submit)
    return token


def get(token):
    """The pending request for a token, or None if unknown or expired."""
    request = _pending.get(token)
    if request is None:
        return None
    if request.is_expired:
        _pending.pop(token, None)
        return None
    return request


def discard(token):
    _pending.pop(token, None)


def render_form(token, fields, error=None):
    """The page a human sees: one password-type input per field, POSTing back
    to this same URL."""
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ''
    inputs = '\n'.join(
        f'<label>{html.escape(field_label)}'
        f'<input type="password" name="{html.escape(field_name)}" required autocomplete="new-password">'
        '</label>'
        for field_name, field_label in fields
    )
    return f"""<!doctype html>
<html>
<head><title>Secure input</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 28rem; margin: 4rem auto; padding: 0 1rem; }}
label {{ display: block; margin-bottom: 1rem; }}
input {{ display: block; width: 100%; padding: 0.5rem; margin-top: 0.25rem; box-sizing: border-box; }}
button {{ padding: 0.5rem 1.5rem; }}
.error {{ color: #b00020; }}
</style>
</head>
<body>
<p>An assistant you're using requested this from an MCP tool. Nothing you enter
here is seen by that assistant.</p>
{error_html}
<form method="post">
{inputs}
<button type="submit">Submit</button>
</form>
</body>
</html>"""


def render_done():
    return """<!doctype html>
<html>
<head><title>Done</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 28rem; margin: 4rem auto; padding: 0 1rem;">
<p>Done. You can return to your assistant.</p>
</body>
</html>"""


def render_gone():
    return """<!doctype html>
<html>
<head><title>Link expired</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 28rem; margin: 4rem auto; padding: 0 1rem;">
<p>This link has expired or was already used. Ask your assistant to try again.</p>
</body>
</html>"""


def render_error(message):
    """A submission the backend rejected. No retry on this link - a submitted request
    is resolved either way, avoiding a race with the polling tool call."""
    return f"""<!doctype html>
<html>
<head><title>Could not complete</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 28rem; margin: 4rem auto; padding: 0 1rem;">
<p class="error" style="color: #b00020;">{html.escape(message)}</p>
<p>Ask your assistant to try again.</p>
</body>
</html>"""


class ElicitationError(Exception):
    """Collecting a secret from the human via a hosted page failed - the link
    expired or was never completed - before any backend call was attempted.
    Raised only from the handshake-era path (_await_secret_handshake_era):
    the modern multi-round-trip path handles the same "link expired" case by
    returning a result dict instead, since a caller there can just retry the
    tool call rather than have it raise."""


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


async def await_secret(fields, message, on_submit):
    """Collects one or more passwords via the pending-request registry above,
    never a tool argument. `fields` is an ordered `[(name, label), ...]`
    list; `on_submit` does the real work once the human submits the page.
    Delegates to the handshake-era variant on an older protocol; otherwise
    this is a stateless multi-round-trip: register + ask, then re-check via
    `request_state` (the token FastMCP echoes back unmodified) until the
    page resolves."""
    ctx = get_context()

    if not _is_modern_protocol(ctx):
        return await _await_secret_handshake_era(ctx, fields, message, on_submit)

    responses = ctx.input_responses

    if responses is None:
        token = register(fields, on_submit)
        return _ask_for_secret(token, message)

    token = ctx.request_state
    pending = get(token)
    if pending is None:
        return {'detail': 'That link expired before it was completed. Please try again.'}

    if not pending.is_resolved:
        return _ask_for_secret(token, message)  # still waiting on the human

    discard(token)
    if pending.error is not None:
        raise BackendAPIError(pending.error)
    return pending.result


async def _await_secret_handshake_era(ctx, fields, message, on_submit):
    token = register(fields, on_submit)
    try:
        consent = await ctx.session.elicit_url(
            message=message,
            url=f'{MCP_BASE_URL}/secrets/{token}',
            elicitation_id=secrets.token_urlsafe(16),
        )
        if consent.action != 'accept':
            return {'detail': 'Cancelled.'}

        pending = get(token)
        while pending is not None and not pending.is_resolved:
            await asyncio.sleep(HANDSHAKE_ERA_POLL_SECONDS)
            pending = get(token)

        if pending is None:
            raise ElicitationError(
                'That link expired before it was completed. Please try again.'
            )
        if pending.error is not None:
            raise BackendAPIError(pending.error)
        return pending.result
    finally:
        discard(token)
