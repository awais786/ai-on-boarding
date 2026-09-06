## Context

See proposal.md - Why. `mcp_server/server.py`'s `CredentialVerifier.verify_token` currently
treats any `django_client.DjangoAPIError` from `exchange_google_token` (401 from Google refusing
the token, or 403 from Django having no account/an embargoed one) the same way: return `None`,
which FastMCP's `RequireAuthMiddleware` turns into an outright refusal before any tool runs.
`django_client.py` is the only module that calls the Django API; every tool goes through it.

## Goals / Non-Goals

**Goals:**
- Let a caller with no Django account reach an MCP session, with access to the signup tool only.
- Add the three tools, backed by Django's existing signup and password-reset endpoints and the
  newly added self-service change-password endpoint.
- Keep every existing tool's behavior for a caller who already has a session credential unchanged.

**Non-Goals:**
- Distinguishing "no account" from "embargoed account" anywhere - Django's own sign-in response
  does not distinguish them (see Decisions), so this system does not either; both are admitted
  to a no-credential session identically.
- Any change to the Django endpoints themselves - signup and both password-reset endpoints are
  used as-is; the self-service change-password endpoint was added in a separate change.
- Rate-limiting signup or password-reset attempts beyond what `ToolCallRateLimiter` already
  applies uniformly to every tool call.

## Decisions

- **Distinguish 401 from 403 in `exchange_google_token`**: today both raise `DjangoAuthError`
  with no way to tell them apart. Split into `DjangoAuthError` (401 - Google refused the token
  itself; stays a hard refusal) and a new `NoDjangoAccountError(DjangoAuthError)` (403 - Django's
  own sign-in endpoint answers identically, same status and body, for "no account" and "matching
  account is embargoed" - a deliberate anti-enumeration choice already shipped and tested in
  `sdd_django_demo/api/mcp_views.py::GoogleAuthView`). Because that response is genuinely
  indistinguishable, `NoDjangoAccountError` covers both, and both are admitted to a
  no-credential session rather than refused outright - narrower than originally proposed (which
  called for keeping embargoed callers refused), corrected here once the shared response made
  that split impossible without reopening the already-reviewed anti-enumeration behavior. An
  embargoed caller reaches no further than anyone else with no credential: every tool but signup
  still refuses them, and signup itself fails as an ordinary duplicate-account refusal since the
  account already exists.
- **Admit rather than refuse on `NoDjangoAccountError`**: `CredentialVerifier.verify_token`
  catches it, strips claims down to `GOOGLE_CLAIMS_TO_KEEP` as it already does on success, and
  caches and returns the verified token with no `DJANGO_TOKEN_CLAIM` set. The caller reaches a
  session; individual tools decide whether they need a credential.
- **A small helper, not a decorator, for the credential check**: every tool except `signup` calls
  a `_require_django_token()` helper at its start that raises a clear `DjangoAPIError` ("no
  account - use the signup tool to create one") when `DJANGO_TOKEN_CLAIM` is absent from the
  caller's claims. A decorator would hide that check from a reader of the tool function; given
  there are only four affected tools, inlining the one-line call is easier to verify against the
  spec than introducing indirection for it.
- **Signup exchanges and caches a credential on success, inline in the tool**: after
  `django_client.signup(...)` succeeds, the tool calls `django_client.exchange_google_token` with
  the caller's own Google token (available via `get_access_token().token`) and, on success, calls
  `_credentials.replace_django_token(...)` so the *cached* entry gains the credential too -
  without this, the next call in the same session would still find no credential cached and ask
  the caller to sign up again immediately after they just did. If the immediate exchange itself
  fails (Django unreachable, or some new refusal), signup still reports success - the account
  exists - and the caller resolves the credential on their next call the normal way, through
  `verify_token`.
- **New `django_client` functions each map one Django endpoint**: `signup`, `request_password_reset`,
  `confirm_password_reset`, `change_own_password`, following the existing pattern of
  `list_users`/`change_password` - one function per endpoint, translating a non-2xx response into
  `DjangoAuthError` (401) or `DjangoAPIError` (everything else), and returning only what a tool
  needs.

## Risks / Trade-offs

- [A caller who will never have an account (declined signup, blocked country) now reaches an MCP
  session instead of being refused immediately] → They still cannot use any tool but signup, and
  every attempt to use another one is refused with a clear "sign up first" message; no Django
  data is reachable without a credential.
- [`NoDjangoAccountError` collapses "no account" and "embargoed" the same way `DjangoAuthError`
  does today] → Matches current behavior exactly; this change does not add or remove any
  distinction a caller could observe.
