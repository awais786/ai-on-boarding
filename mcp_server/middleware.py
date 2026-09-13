"""Audit logging around every tool call."""

import logging

from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware

from config import TOOL_CALL_LOG_FILE

logger = logging.getLogger('mcp_server')
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.FileHandler(TOOL_CALL_LOG_FILE)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)

# Defensive only: no tool takes a password as a plain argument today (each is
# elicited instead - see server.py), but a future regression still won't be logged.
REDACTED_ARGS = ('password', 'current_password', 'new_password')


def _caller_id():
    """The signed-in caller's Google subject, or 'anonymous' outside a request."""
    access_token = get_access_token()
    return access_token.claims.get('sub', 'unknown') if access_token else 'anonymous'


class ToolCallLogger(Middleware):
    """Logs every tool call - caller, tool, arguments - and whether it succeeded."""

    def __init__(self, redact=REDACTED_ARGS):
        self._redact = redact

    async def on_call_tool(self, context, call_next):
        caller = _caller_id()
        tool = context.message.name
        args = {
            key: ('***' if key in self._redact else value)
            for key, value in (context.message.arguments or {}).items()
        }

        try:
            result = await call_next(context)
        except Exception:
            logger.exception('tool call failed: caller=%s tool=%s args=%s', caller, tool, args)
            raise

        logger.info('tool call: caller=%s tool=%s args=%s', caller, tool, args)
        return result
