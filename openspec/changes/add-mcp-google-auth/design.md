## Context

See proposal.md - Why. Today: no authentication at all on the MCP server (`mcp_server/my_server.py`
- `FastMCP("Practice-MCP-Server")` has no `auth=`); no social-auth or external-identity mapping
anywhere in `sdd_django_demo`; `django.contrib.auth.User` with no custom fields; DRF token auth
via `rest_framework.authtoken`; `SigninView` (`api/views.py`) is the existing pattern for
"validate → find user → check embargo → issue/reuse Token → return `{"token": ...}`".
`AccountCountry` (`embargo/models.py`) is the existing pattern for a small `OneToOneField(User)`
side-table. `settings.py`'s `DJANGO_ALLOWED_HOSTS` is the existing pattern for a comma-separated
env var parsed into a list. Neither `sdd_django_demo/requirements.txt` nor the MCP project's
`pyproject.toml` currently includes a Django-side HTTP client.

## Goals / Non-Goals

**Goals:**
- Gate every MCP tool behind a real Google OAuth login, using FastMCP's built-in `GoogleProvider`
  exactly as documented, with no custom `load_access_token` override.
- Give Django a way to turn a verified Google access token into its existing DRF token, with no
  new Django dependency and no second token type.
- Persist the Google `sub` → Django `User` link so a later change to the Google account's email
  doesn't sever it.
- Enforce the same embargo rule the password-based signin flow already enforces.

**Non-Goals:**
- No account auto-provisioning: a verified Google identity with no matching Django account is
  rejected, not signed up (per proposal.md and the confirmed decision above).
- No retrofitting of explicit response-field allowlists onto the *existing* MCP tool wrappers
  (`get_users`, `password_reset`, `update_password`) - only the new Google-auth exchange path is
  built with one from the start, per "keep the implementation minimal and scoped to MCP
  authentication; do not modify unrelated MCP tools."
- No `TokenCache` / persistent MCP token storage - the default in-memory FastMCP flow is enough
  for v1; a cache is optional future work, not built here.
- No change to `/api/signup/`, `/api/signin/`, or `/api/password-reset/` behaviour.

## Decisions

### New Django model: `GoogleIdentity`
Added to `sdd_django_demo/api/models.py`, mirroring `AccountCountry`'s shape:
```python
class GoogleIdentity(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    google_sub = models.CharField(max_length=255, unique=True)
```
One migration. Justified by the "Map a verified Google identity (`sub`) to a Django account,
independent of email" and "First successful authentication links the identity" requirements -
matching by email alone (no new model) cannot survive an email change on the Google side and was
explicitly rejected above. `on_delete=CASCADE` matches `AccountCountry` and `PasswordResetCode`;
deleting a `User` should not leave an orphaned identity link.

### New endpoint: `POST /api/auth/google/`
New `GoogleSigninView` (DRF `GenericAPIView`, same shape as `SigninView`) + `GoogleSigninSerializer`
(one field: `access_token`) in the existing `api` app - no new Django app, per "prefer the
simplest design" and because this endpoint's job (validate → find user → check embargo → issue
token) is identical in shape to `SigninView`'s. Reuses the existing `TokenSerializer` for the
response body, so the response shape is byte-identical to `/api/signin/`'s success response -
satisfies "return the application's existing DRF token" and "no field not already part of that
existing token response."

Verification order (each a rejection point per the spec's requirements):
1. `access_token` present (serializer validation, 400 on absence - matches `SigninSerializer`'s
   missing-field handling).
2. Call Google's tokeninfo endpoint with the token; a non-200 response means invalid/expired
   (401).
3. `aud` claim is in `settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS` (401 if not).
4. `email_verified` claim is true (401 if not).
5. If `settings.GOOGLE_OAUTH_ALLOWED_DOMAINS` is non-empty, `hd` claim is in that list (401 if
   not; a token with no `hd` claim at all is treated as not on the allowlist).
6. Look up `GoogleIdentity` by `sub`; if found, use its `user`. Otherwise look up `User` by
   `email__iexact` against the verified email; if found, create the `GoogleIdentity` link now.
   If neither resolves, reject (401) - no account is created.
7. `is_user_embargoed(user)` (reused from `embargo.rules`, same call `SigninView` makes) - 401 if
   embargoed.
8. `Token.objects.get_or_create(user=user)`, return `{"token": token.key}` - identical to
   `SigninView`'s success path.

All rejection points return 401 with a `{"detail": "..."}` body (message text chosen per
rejection point during implementation - the spec fixes status/shape, not exact wording). Unlike
`SigninView`, these bodies are allowed to differ per reason: the caller already holds a valid
Google access token proving ownership of that Google identity, so telling them *why* their own
authentication attempt failed does not create an enumeration oracle against someone else's
account the way password-signin's uniform rejection does.

### Google token verification: stdlib `urllib`, two calls, no new dependency
Revised during implementation: a single tokeninfo call cannot be confirmed to carry every claim
this design needs. Google's own tokeninfo documentation frames `sub`/`email_verified`/`hd` as
**ID-token** claims (`?id_token=...`) and separately warns the endpoint "is not suitable for use
in production code" generally; for an **access token** (`?access_token=...`, what
`GoogleProvider` actually hands the MCP tool), tokeninfo is confirmed to return `aud`, `sub`,
`email`, and `email_verified`, but `hd` is not confirmed for that variant anywhere in Google's
documentation. Two calls, each used only for the claim(s) Google actually documents on it:

1. `GET https://oauth2.googleapis.com/tokeninfo?access_token=<token>` - used only for `aud`
   (this endpoint can tell you what client an opaque access token was issued to; the userinfo
   endpoint below cannot).
2. `GET https://openidconnect.googleapis.com/v1/userinfo` with `Authorization: Bearer <token>` -
   used for `sub`, `email`, `email_verified`, and `hd` (Google's documented, production-supported
   way to get profile claims from an access token).

Both via `urllib.request.urlopen` - still no `requests`/`httpx` addition to
`sdd_django_demo/requirements.txt` (confirmed decision holds; it is now two GETs instead of one,
not a new dependency). Either call returning non-2xx, or any `URLError`/`HTTPError`/JSON-decode
failure, is treated as "invalid token" (401) - the same broad-but-logged pattern
`try_deliver_reset_link` (`api/views.py`) already uses for "nothing here can leak past this call
as a 500."

### Django settings additions
Both follow `DJANGO_ALLOWED_HOSTS`'s exact comma-separated-env-var-to-list pattern
(`settings.py`):
- `GOOGLE_OAUTH_ALLOWED_CLIENT_IDS` - comma-separated Google OAuth client IDs accepted as `aud`.
  Empty by default, meaning no token can pass verification until a deployment sets it -
  fail-closed default, not fail-open.
- `GOOGLE_OAUTH_ALLOWED_DOMAINS` - comma-separated hosted domains. Empty by default, meaning no
  `hd` restriction is applied (matches the spec's "no domain allowlist configured" requirement,
  and lets personal `@gmail.com` accounts - which carry no `hd` claim at all - authenticate).

Kept as two independently configurable settings (not reused from any single "the" client ID) so
MCP's own Google OAuth app registration and a possible future separate Django-side registration
can both be added to the same allowlist without a code change - per proposal.md's "support
separate MCP and Django Google OAuth registrations later."

### MCP server: `GoogleProvider` gates the whole server
```python
from fastmcp.server.auth.providers.google import GoogleProvider

mcp = FastMCP(
    "Practice-MCP-Server",
    auth=GoogleProvider(
        client_id=os.environ["GOOGLE_MCP_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_MCP_CLIENT_SECRET"],
        base_url=os.environ.get("GOOGLE_MCP_BASE_URL", "http://127.0.0.1:8080"),
        required_scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
    ),
)
```
No `load_access_token` override (confirmed decision from the agreed design) - the default
FastMCP/Google verification flow is used as-is; `client_id`/`client_secret` are required env
vars (no insecure fallback, unlike Django's `DJANGO_SECRET_KEY` pattern - there is no safe
placeholder for an OAuth client secret). This is server-wide, so every existing tool
(`greet`, `signup`, `signin`, `get_users`, `password_reset`, `update_password`) now requires a
Google-authenticated MCP session first, purely as a consequence of how `auth=` on `FastMCP`
works - none of their code changes.

### New MCP tool: `google_signin`
```python
@mcp.tool
async def google_signin():
    """Exchange the caller's Google-authenticated MCP session for a Django token."""
    global _token
    google_token = get_access_token()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{DJANGO_BASE_URL}/api/auth/google/",
            json={"access_token": google_token.token},
        )
    if response.status_code == 401:
        return {"status": "failed", "detail": "Unable to authenticate with the provided Google session."}
    response.raise_for_status()
    _token = response.json()["token"]
    return {"status": "success"}
```
Follows `signin`'s existing shape exactly: caches `_token` at module scope, returns only
`{"status": ...}` to the caller. `google_token.token` (the raw Google access token) and the
Django token are both read into local variables and never placed in the returned dict - this
*is* the endpoint-scoped "explicit response-field allowlist" the agreed design calls for: the
only field ever returned is `status` (and `detail` on failure), matching every other tool in this
file. Since `/api/auth/google/`'s response body is already just `{"token": ...}`, there is
nothing else to filter on the Django-response side.

## Risks / Trade-offs

- [Risk] Local development for the MCP server now hard-requires a real Google OAuth client
  registration - the "no environment variables required to run or test" convention that holds for
  `sdd_django_demo` does not extend to `mcp_server`. → Mitigation: this is the explicitly agreed
  design (FastMCP's `GoogleProvider`, no bypass), so it is documented rather than avoided - a
  local-dev section in this change's tasks covers registering a free Google Cloud OAuth client
  (Desktop or Web app type, redirect URI `http://127.0.0.1:8080/auth/callback`, the test user
  added to the consent screen) and setting `GOOGLE_MCP_CLIENT_ID`/`GOOGLE_MCP_CLIENT_SECRET`.
- [Risk] Django's tokeninfo call is a new synchronous network dependency at request time. →
  Mitigation: failure (timeout, non-2xx, malformed JSON) is caught and treated as "invalid token"
  (401), never a 500; logged the way `try_deliver_reset_link` already logs a swallowed failure.
  No retry/backoff for v1 - acceptable for a teaching/demo deployment.
- [Risk] `GoogleIdentity.google_sub` is the only thing standing between "known Google identity"
  and "re-linked to a different account" if a row were ever edited by hand. → Mitigation: no
  code path updates an existing `GoogleIdentity` row once created (only "not found → create" is
  implemented, matching the spec's "first successful authentication links the identity"); a
  deliberate re-link is a manual/admin operation, out of scope here.
- [Risk] For a local Google Cloud project, MCP's client ID is the only one that will ever appear
  in Google-issued tokens, making `GOOGLE_OAUTH_ALLOWED_CLIENT_IDS` a single-entry allowlist in
  practice today. → Not a real risk, just a note: the setting is still a list so a future,
  separate Django-side Google OAuth registration is a config change, not a code change.

## Migration Plan

One new Django migration (`api` app) adding `GoogleIdentity`. No data backfill - the table starts
empty and is populated only by first-time successful Google authentications. Rollback: revert the
code and migration; no existing feature reads or writes this table, so there is no data-loss risk
in rolling back.

## Open Questions

- Exact wording of each `{"detail": "..."}` rejection message is left to implementation (the spec
  fixes status code and body shape, not literal text) - does not affect the spec, approach, or
  task breakdown.
