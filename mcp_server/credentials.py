"""Embeds a caller's Django token in the FastMCP-signed JWT itself, verified
locally on every later request - no repeat Google call, no repeat Django
exchange, no server-side session state.
"""

from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider

import django_client

DJANGO_TOKEN_CLAIM = 'django_token'
GOOGLE_TOKEN_CLAIM = 'google_token'  # kept to re-exchange a stale Django token mid-session


class DjangoGoogleProvider(GoogleProvider):
    async def _extract_upstream_claims(self, idp_tokens):
        google_token = idp_tokens['access_token']

        verified = await self._token_validator.verify_token(google_token)
        if verified is None:
            raise RuntimeError('Google refused the token being exchanged at login.')

        claims = {'sub': verified.claims.get('sub'), 'email': verified.claims.get('email')}

        try:
            claims[DJANGO_TOKEN_CLAIM] = await django_client.exchange_google_token(google_token)
            claims[GOOGLE_TOKEN_CLAIM] = google_token
        except django_client.DjangoAPIError as err:
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
