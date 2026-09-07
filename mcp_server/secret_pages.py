"""Collects a password directly from a human's browser via URL-mode elicitation
(SEP-1036) - never through the MCP protocol, client, or model (see server.py).

A pending request's `on_submit` closure does the real Django call the moment
the page is submitted. The waiting tool call only ever learns whether it
resolved, and to what result - never the password itself.
"""

import html
import secrets
import time

TOKEN_BYTES = 32
PENDING_TTL_SECONDS = 15 * 60  # a human might take a while to open the link


class PendingSecretRequest:
    """One outstanding "collect a password" request. `fields` is an ordered
    [(name, label), ...] list - one entry for most operations, two for
    change_my_password (current, then new)."""

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
    """A submission Django rejected. No retry on this link - a submitted request
    is resolved either way, avoiding a race with the polling tool call."""
    return f"""<!doctype html>
<html>
<head><title>Could not complete</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 28rem; margin: 4rem auto; padding: 0 1rem;">
<p class="error" style="color: #b00020;">{html.escape(message)}</p>
<p>Ask your assistant to try again.</p>
</body>
</html>"""
