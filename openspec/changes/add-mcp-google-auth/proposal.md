## Why

The MCP server has no authentication at all today - any MCP client can call every tool,
including `get_users` and `update_password`, without ever signing in to Google or Django. We
want the MCP server to require a real Google login before any tool runs, and to bridge that
Google identity to the app's existing account system (a DRF token) rather than inventing a
second, parallel authentication mechanism for the API.

## What Changes

- The MCP server now requires callers to authenticate with Google before any tool call
  succeeds (FastMCP's own Google OAuth login flow, enforced server-wide).
- Add a new Django endpoint that accepts a Google access token, independently verifies it with
  Google, and only then issues the app's existing DRF token - the same kind of token
  `/api/signin/` already returns.
- Verification rejects a token whose audience is not on a configured allowlist, whose email is
  not verified by Google, or - where the deployment configures allowed domains - whose hosted
  domain (`hd`) is not on that allowlist.
- The verified Google identity is matched to a Django account by a persisted mapping (Google's
  `sub`, not just email) so a later change to the Google account's email address doesn't sever
  the link. **No account is created by this flow** - a Google identity with no matching Django
  account is rejected, not signed up.
- A new MCP tool lets a caller (already Google-authenticated at the MCP layer) exchange that
  session for a DRF token, cached the same way `signin` caches one today, so `get_users`,
  `update_password`, etc. keep working unchanged.
- **BREAKING**: every existing MCP tool (`greet`, `signup`, `signin`, `get_users`,
  `password_reset`, `update_password`) now requires a Google-authenticated MCP session first -
  none of them are reachable anonymously anymore.

## Capabilities

### New Capabilities
- `google-signin`: lets a caller holding a verified Google access token obtain the app's
  existing DRF authentication token, without introducing a second token type or changing what
  that token can do.

### Modified Capabilities
(none - `user-signup`, `user-signin`, and `user-password-reset` are unchanged; a Google-verified
caller receives the exact same kind of token those flows already issue)

## Impact

- New Django endpoint under `sdd_django_demo/api/` (new view, serializer, and URL route) plus a
  new model mapping a Google `sub` to a `User` (one migration).
- New Django settings: a comma-separated allowlist of accepted Google OAuth client IDs
  (mirroring the existing `DJANGO_ALLOWED_HOSTS` env-var pattern) and an optional comma-separated
  allowlist of accepted hosted domains. No new Django dependency - token verification uses a
  single stdlib `urllib` call to Google's tokeninfo endpoint.
- `mcp_server/my_server.py`: `FastMCP(...)` gains `auth=GoogleProvider(...)`, configured from new
  environment variables (Google OAuth client ID/secret for the MCP server's own registration,
  kept distinct from Django's client-ID allowlist so the two can use separate Google OAuth app
  registrations). One new tool performs the Google-token-for-DRF-token exchange; no existing
  tool's code changes.
- New dependency for the MCP project: none beyond what FastMCP's Google support already needs
  (`fastmcp[apps]` is already a dependency; no version bump anticipated, to be confirmed in
  design.md).
- Local development now requires a real (free) Google OAuth client registration to exercise the
  MCP server at all, where today it requires no external setup - documented in design.md.
