"""Authentication and the caller's backend credential: verifying Google
identity at login, and calling the backend with the caller's own,
possibly-stale, token.

Not to be confused with elicitation.py, which collects a secret from the
human via a hosted page - a related but separate concern (see that module's
own docstring).
"""

from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token

import clients.account_client as account_client  # module-qualified: exchange_google_token is a test seam (see tests/conftest.py)
from clients.base_client import BackendAPIError

BACKEND_TOKEN_CLAIM = 'backend_token'
GOOGLE_TOKEN_CLAIM = 'google_token'  # kept to re-exchange a stale backend token mid-session

SIGN_IN_AGAIN = 'Your session is no longer valid. Please sign in again.'  # never hints at a token
NEED_TO_SIGN_UP = 'No account found for this Google identity. Use the signup tool to create one.'


class BackendGoogleProvider(GoogleProvider):
    """Embeds a caller's backend token in the FastMCP-signed JWT itself,
    verified locally on every later request - no repeat Google call, no
    repeat backend exchange, no server-side session state."""

    async def _extract_upstream_claims(self, idp_tokens):
        google_token = idp_tokens['access_token']

        verified = await self._token_validator.verify_token(google_token)
        if verified is None:
            raise RuntimeError('Google refused the token being exchanged at login.')

        claims = {'sub': verified.claims.get('sub'), 'email': verified.claims.get('email')}

        try:
            claims[BACKEND_TOKEN_CLAIM] = await account_client.exchange_google_token(google_token)
            claims[GOOGLE_TOKEN_CLAIM] = google_token
        except account_client.BackendAPIError as err:
            if not err.no_account:
                raise
            # identity is fine, no account yet - admit the session anyway so `signup` is reachable

        return claims

    async def load_access_token(self, token):
        try:
            payload = self.jwt_issuer.verify_token(token)
        except Exception:
            return None

        upstream_claims = payload.get('upstream_claims')
        if upstream_claims is None:
            # not one of our tokens - fall back to the default reverify-with-Google path
            return await super().load_access_token(token)

        return AccessToken(
            token=token,
            client_id=payload.get('client_id', ''),
            scopes=payload.get('scope', '').split(),
            expires_at=payload.get('exp'),
            subject=upstream_claims.get('sub'),
            claims=dict(upstream_claims),
        )


def require_backend_token():
    """Raise a clear refusal if the caller's session has no backend credential yet."""
    if BACKEND_TOKEN_CLAIM not in get_access_token().claims:
        raise BackendAPIError(NEED_TO_SIGN_UP)


async def call_backend(client_cls, method, *args, access_token=None, **kwargs):
    """Call method(client, ...) on a fresh client_cls(backend_token) - e.g.
    `call_backend(UsersClient, UsersClient.list_users)` - refreshing a
    refused token once before giving up. Pass `access_token` explicitly when
    calling from outside a live MCP request (a secret page's `on_submit`);
    default is the current session's.

    `client_cls` is required, not defaulted, so a caller can only construct
    the client whose class it actually imported - the account tools have no
    way to reach UsersClient.change_password through this helper, and vice
    versa.

    The backend token lives inside the caller's signed JWT (see
    BackendGoogleProvider above), so a fresh one obtained here can't be
    written back into it - it only covers this one call.
    """
    if access_token is None:
        access_token = get_access_token()

    async def _attempt(backend_token):
        client = client_cls(backend_token)
        return await method(client, *args, **kwargs)

    try:
        return await _attempt(access_token.claims[BACKEND_TOKEN_CLAIM])
    except BackendAPIError as err:
        if not err.stale_credential:
            raise

    try:
        google_token = access_token.claims[GOOGLE_TOKEN_CLAIM]
        backend_token = await account_client.exchange_google_token(google_token)
    except BackendAPIError:
        raise BackendAPIError(SIGN_IN_AGAIN) from None

    try:
        return await _attempt(backend_token)
    except BackendAPIError as err:
        if not err.stale_credential:
            raise
        raise BackendAPIError(SIGN_IN_AGAIN) from None
