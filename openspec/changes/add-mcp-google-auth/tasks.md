## 1. Django settings and dependencies

- [x] 1.1 Add `GOOGLE_OAUTH_ALLOWED_CLIENT_IDS` to `sdd_django_demo/sdd_django_demo/settings.py`
  (comma-separated env var parsed into a list, empty by default), following
  `DJANGO_ALLOWED_HOSTS`'s exact pattern, and verify it parses an empty and a multi-value string
  correctly via the Django shell
- [x] 1.2 Add `GOOGLE_OAUTH_ALLOWED_DOMAINS` the same way, empty by default
- [x] 1.3 Confirm no new entry is needed in `sdd_django_demo/requirements.txt` - verification uses
  only `urllib` (stdlib)

## 2. Google token verification

- [x] 2.1 Add a `verify_google_access_token(access_token)` helper (new module,
  `sdd_django_demo/api/google_auth.py`) that calls tokeninfo (for `aud`) and userinfo (for `sub`,
  `email`, `email_verified`, `hd`) via `urllib.request.urlopen` and returns the merged claims, or
  `None` on any non-2xx response, network error, or malformed JSON from either call - revised
  from a single tokeninfo call during implementation, see design.md; verify manually against a
  deliberately invalid token before wiring it into the view
- [x] 2.2 Add `GoogleIdentity` model to `sdd_django_demo/api/models.py`
  (`user = OneToOneField(User, on_delete=CASCADE)`, `google_sub = CharField(unique=True)`) and
  generate the migration; verify `manage.py migrate` applies cleanly on a fresh database

## 3. Endpoint

- [x] 3.1 Add `GoogleSigninSerializer` (`access_token`, required, non-blank) to
  `sdd_django_demo/api/serializers.py`
- [x] 3.2 Implement `GoogleSigninView` (`generics.GenericAPIView`) in
  `sdd_django_demo/api/views.py`: validate the serializer, call
  `verify_google_access_token`, check `aud` against `GOOGLE_OAUTH_ALLOWED_CLIENT_IDS`, check
  `email_verified`, check `hd` against `GOOGLE_OAUTH_ALLOWED_DOMAINS` when that setting is
  non-empty, resolve the Django account (`GoogleIdentity` lookup by `sub`, falling back to
  `User.objects.filter(email__iexact=...)` and creating the `GoogleIdentity` link on first match),
  reject if unresolved, check `is_user_embargoed` (reusing `embargo.rules`), then
  `Token.objects.get_or_create` and return `TokenSerializer`'s `{"token": ...}` shape - matching
  every rejection point to a requirement in `specs/google-signin/spec.md`
- [x] 3.3 Add the `auth/google/` route to `sdd_django_demo/api/urls.py`
- [x] 3.4 Add drf-spectacular schema annotations documenting the success and every rejection
  response

## 4. MCP server

- [x] 4.1 Add `fastmcp.server.auth.providers.google.GoogleProvider` as `mcp_server/my_server.py`'s
  `FastMCP(..., auth=...)`, reading `GOOGLE_MCP_CLIENT_ID`, `GOOGLE_MCP_CLIENT_SECRET` (both
  required, no fallback), and `GOOGLE_MCP_BASE_URL` (defaulting to `http://127.0.0.1:8080`) from
  the environment
- [x] 4.2 Add the `google_signin` tool: read the caller's Google access token via
  `fastmcp.server.dependencies.get_access_token()`, POST it to `/api/auth/google/`, cache the
  returned DRF token in FastMCP's session-scoped Context state (`get_context().set_state(...)`)
  and return only `{"status": ...}` - never the Google token or the DRF token
- [x] 4.3 Leave every other existing tool (`greet`, `signup`, `signin`, `get_users`,
  `password_reset`, `update_password`) unmodified

## 5. Local-development configuration

- [x] 5.1 Document (in this change's tasks, or a short local-dev note) how to register a free
  Google Cloud OAuth client for local testing: OAuth consent screen with a test user, redirect URI
  `http://127.0.0.1:8080/auth/callback`, and the resulting client ID/secret exported as
  `GOOGLE_MCP_CLIENT_ID`/`GOOGLE_MCP_CLIENT_SECRET` - see the note below
- [x] 5.2 Document setting `GOOGLE_OAUTH_ALLOWED_CLIENT_IDS` to that same client ID for local
  Django, and confirm the end-to-end flow (MCP Google login → `google_signin` tool → any other
  tool) works against a local `runserver` and a local MCP server - see the note below;
  end-to-end confirmation deferred to a real Google Cloud project (not available in this
  environment) and re-checked in this change's Tests section instead, against Django directly

### Local-development note

Local development for `mcp_server/` now requires a real (free) Google OAuth client - there is no
bypass, per the agreed design. One-time setup:

1. In the [Google Cloud Console](https://console.cloud.google.com/), create a project (or reuse
   one) and configure the OAuth consent screen in "External" testing mode, adding your own Google
   account as a test user.
2. Create an OAuth 2.0 Client ID (type "Web application"). Add
   `http://127.0.0.1:8080/auth/callback` as an authorized redirect URI - this is FastMCP's default
   `redirect_path` for `GoogleProvider`, matching `GOOGLE_MCP_BASE_URL`'s default of
   `http://127.0.0.1:8080`.
3. Export the resulting client ID/secret before running the MCP server:
   ```bash
   export GOOGLE_MCP_CLIENT_ID="<client-id>.apps.googleusercontent.com"
   export GOOGLE_MCP_CLIENT_SECRET="<client-secret>"
   ```
4. For Django, add that same client ID to the audience allowlist (today, MCP and Django share one
   Google Cloud project locally, so it is the only entry - see design.md on why this is still a
   list):
   ```bash
   export GOOGLE_OAUTH_ALLOWED_CLIENT_IDS="<client-id>.apps.googleusercontent.com"
   ```
   Leave `GOOGLE_OAUTH_ALLOWED_DOMAINS` unset unless testing the domain-restriction requirement -
   unset means no `hd` restriction is applied.
5. Run `manage.py runserver` and `python mcp_server/my_server.py` as usual; an MCP client now
   needs to complete a Google login before any tool call succeeds.

## 6. Tests (after implementation, from the spec)

- [x] 6.1 List every requirement in `specs/google-signin/spec.md` and what a test would need to
  assert, working only from the spec
- [x] 6.2 Write `sdd_django_demo/api/test_google_signin.py` from that list, covering: successful
  authentication and token issuance; missing `access_token` field; invalid/expired token; audience
  not on the allowlist; audience on the allowlist; unverified email; domain allowlist configured
  and not matched; domain allowlist configured and matched; no domain allowlist configured (an
  `hd`-bearing and an `hd`-less token both succeed); previously-linked identity signs in again
  and lands on the same account after an email change; first-time login links a matching
  existing account; no matching account is rejected and creates nothing; embargoed mapped account
  is rejected; success response contains only the application token
- [x] 6.3 Run `pytest` and confirm all tests pass - 174 passed (15 new, 159 pre-existing, no
  regressions)
- [x] 6.4 Prove at least one new test can fail - break one rejection check on purpose (e.g. skip
  the `aud` allowlist check), confirm the matching test goes red, then restore it - disabled the
  `aud` allowlist check, confirmed `test_google_signin_rejects_unrecognised_audience` failed
  (200 instead of 401), restored it, confirmed all 15 tests pass again

## 7. Traceability and review

- [x] 7.1 Build `traceability.md` mapping every requirement in `specs/google-signin/spec.md` to
  its code and test
- [x] 7.2 Run `/code-review` - round 1: 9 findings, all confirmed
- [x] 7.3 Fix any blocking findings (cited to a requirement, a named failing test, or a documented
  convention) - fixed: embargo-before-link ordering (spec requirement), unordered email lookup
  (existing `PasswordResetRequestView` convention), narrow except clause and missing logging in
  `google_auth.py` (contradicted design.md's own stated behavior), no test exercising real
  verification logic (config.yaml's security-sensitive-test convention), IntegrityError race on
  first-time link creation, and `get_access_token()` None-guard (matches this file's existing
  defensive pattern) - see traceability.md's Notes for the two remaining nits recorded, not fixed
- [x] 7.4 Run `/code-review` again (follow-up pass) - round 2: 5 findings. Fixed (all cite a
  requirement or a documented convention): an empty/missing `email` claim falling back to `''`
  and matching a blank-email account instead of being rejected (violates the "no linked or
  matching account" requirement); a missing `sub` claim being misattributed to the
  concurrent-creation race and silently swallowed with no log entry (extends the same
  design.md logging convention fixed in round 1); the duplicated `GoogleIdentity` lookup query
  (extracted to `_find_google_identity`, closing the drift risk the reviewer flagged); no test
  for the MCP tool's token-non-exposure property (added `mcp_server/test_google_signin_tool.py`,
  stdlib `unittest` only - no new dependency, unlike adding pytest for `mcp_server/` would have
  been). Recorded as a nit, not fixed: `GoogleSigninView` has no throttle - a real operational
  concern, but not cited to any requirement, test, or documented convention, and adding one is an
  undecided design choice (which key? per-IP?) outside this change's proposal. Full suite: 183
  passed (2 more from this round's fixes), no regressions. Per config.yaml's two-pass cap, this
  session's own analysis stands as the final verdict rather than invoking a third automated pass:
  **Ready to merge: yes**
- [x] 7.5 Ensure a GitHub issue exists for this change (`gh issue create` if none does) and post
  the proposal and the full delta spec to it via `gh issue comment` - confirmed with the user
  first (per standing guidance to always confirm before commenting on a shared issue); posted to
  existing issue #46 (`awais786/ai-on-boarding`, the broader MCP-tools parent issue) rather than
  creating a new one, per the user's choice: proposal.md at
  https://github.com/awais786/ai-on-boarding/issues/46#issuecomment-5561854454, delta spec at
  https://github.com/awais786/ai-on-boarding/issues/46#issuecomment-5561855073
