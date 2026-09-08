"""Stdlib-only (no pytest) so it needs no new dependency for mcp_server/.

Run with: .venv/bin/python -m unittest mcp_server/test_google_signin_tool.py
"""
import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault('GOOGLE_MCP_CLIENT_ID', 'test-client-id')
os.environ.setdefault('GOOGLE_MCP_CLIENT_SECRET', 'test-client-secret')

sys.path.insert(0, str(Path(__file__).resolve().parent))
import my_server  # noqa: E402
from fastmcp.server.context import Context, set_context  # noqa: E402


class _FakeSession:
    """Stands in for a real ServerSession: just enough for Context.session_id to
    resolve to a fixed, caller-chosen value instead of raising outside a real request."""

    def __init__(self, session_id):
        self._fastmcp_state_prefix = session_id


def _context_for_session(session_id):
    """A context manager that makes get_state/set_state resolve under `session_id`,
    mirroring how a real MCP client's session isolates its cached token."""
    return set_context(Context(my_server.mcp, session=_FakeSession(session_id)))


def _fake_async_client(response):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=response)
    return client


class GoogleSigninToolTests(unittest.TestCase):
    """Directly asserts the never-expose-tokens property - security-sensitive behaviour
    needs a test that asserts it directly, per openspec/config.yaml."""

    def test_response_never_contains_the_google_or_django_token(self):
        fake_google_token = MagicMock(token='super-secret-google-access-token')
        fake_response = MagicMock(status_code=200)
        fake_response.json.return_value = {'token': 'super-secret-django-token'}
        fake_response.raise_for_status.return_value = None

        async def _run():
            with _context_for_session('test-session'):
                return await my_server.google_signin()

        with patch.object(my_server, 'get_access_token', return_value=fake_google_token), \
                patch.object(
                    my_server.httpx, 'AsyncClient',
                    return_value=_fake_async_client(fake_response),
                ):
            result = asyncio.run(_run())

        self.assertEqual(result, {'status': 'success'})
        self.assertNotIn('super-secret-google-access-token', repr(result))
        self.assertNotIn('super-secret-django-token', repr(result))

    def test_token_is_isolated_per_mcp_session(self):
        """Two callers signed in under different MCP sessions must not share a cached
        token - a shared module-level global previously let one session's signin
        silently overwrite another's, leaking one identity's session into another's
        requests."""
        async def _signin_and_get_token(session_id, token_value):
            with _context_for_session(session_id):
                fake_response = MagicMock(status_code=200)
                fake_response.json.return_value = {'token': token_value}
                fake_response.raise_for_status.return_value = None
                with patch.object(
                    my_server.httpx, 'AsyncClient',
                    return_value=_fake_async_client(fake_response),
                ):
                    await my_server.signin('someone', 'password')
                return await my_server._get_token()

        token_a = asyncio.run(_signin_and_get_token('session-a', 'token-for-a'))
        token_b = asyncio.run(_signin_and_get_token('session-b', 'token-for-b'))

        self.assertEqual(token_a, 'token-for-a')
        self.assertEqual(token_b, 'token-for-b')

    def test_no_authenticated_google_session_is_reported_without_crashing(self):
        with patch.object(my_server, 'get_access_token', return_value=None):
            result = asyncio.run(my_server.google_signin())

        self.assertEqual(result['status'], 'error')

    def test_rejected_django_authentication_is_reported_without_crashing(self):
        fake_google_token = MagicMock(token='some-google-access-token')
        fake_response = MagicMock(status_code=401)

        with patch.object(my_server, 'get_access_token', return_value=fake_google_token), \
                patch.object(
                    my_server.httpx, 'AsyncClient',
                    return_value=_fake_async_client(fake_response),
                ):
            result = asyncio.run(my_server.google_signin())

        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('some-google-access-token', repr(result))


if __name__ == '__main__':
    unittest.main()
