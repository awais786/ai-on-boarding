## 1. django_client: distinguish "no account" and add new endpoint functions

- [x] 1.1 In `mcp_server/django_client.py`, add `NoDjangoAccountError(DjangoAuthError)` and have
  `exchange_google_token` raise it for a 403 response, keeping `DjangoAuthError` for a 401
- [x] 1.2 Add `signup(email, username, password, country)` calling `POST /signup/` with no auth
  header, raising `DjangoAPIError` on any non-200 response (validation failures included), and
  returning `{'detail': 'Account created.'}` on success
- [x] 1.3 Add `request_password_reset(email)` calling `POST /password-reset/`, returning Django's
  own generic response body unchanged (it is already identical for every address)
- [x] 1.4 Add `confirm_password_reset(code, new_password)` calling `POST
  /password-reset/confirm/`, raising `DjangoAPIError` on a non-200 response and returning
  `{'detail': 'Password changed.'}` on success
- [x] 1.5 Add `change_own_password(django_token, current_password, new_password)` calling `POST
  /users/me/change-password/` with the caller's own token, raising `DjangoAuthError` on 401 and
  `DjangoAPIError` on any other non-200 response

## 2. server.py: admit a caller with no account, gate the other tools

- [x] 2.1 In `CredentialVerifier.verify_token`, catch `NoDjangoAccountError` separately from
  `DjangoAuthError`/`DjangoAPIError`: strip claims to `GOOGLE_CLAIMS_TO_KEEP` as on success, cache
  the entry with no `DJANGO_TOKEN_CLAIM`, and return it instead of `None`
- [x] 2.2 Add a `_require_django_token()` helper that raises `django_client.DjangoAPIError` with
  a message telling the caller to use the signup tool when the current access token's claims have
  no `DJANGO_TOKEN_CLAIM`
- [x] 2.3 Call `_require_django_token()` at the start of `list_signup_users`,
  `list_users_by_country`, and `change_user_password`, before they touch `_call_django`

## 3. New tools

- [x] 3.1 Add a `signup(email, username, password, country)` tool: calls
  `django_client.signup`, then tries `django_client.exchange_google_token` on the caller's own
  Google token and `_credentials.replace_django_token(...)` on success; the tool reports signup's
  own outcome regardless of whether the immediate exchange succeeds
- [x] 3.2 Add a `request_password_reset(email)` tool calling `django_client.request_password_reset`
  - no credential required, callable with or without a session credential
- [x] 3.3 Add a `reset_password(code, new_password)` tool calling
  `django_client.confirm_password_reset` - no credential required
- [x] 3.4 Add a `change_my_password(current_password, new_password)` tool: calls
  `_require_django_token()` then `_call_django(django_client.change_own_password,
  current_password, new_password)`

## 4. Tests (after implementation, from the spec)

- [x] 4.1 List every scenario in `specs/mcp-session-auth/spec.md`'s MODIFIED/ADDED sections and
  `specs/mcp-auth-tools/spec.md`, and what a test would need to assert, working only from the spec
- [x] 4.2 Add tests in `mcp_server/tests/test_django_client.py` for `signup`,
  `request_password_reset`, `confirm_password_reset`, `change_own_password`, and the 401/403
  split in `exchange_google_token`, following the existing respx-mocked style in that file
- [x] 4.3 Add tests in `mcp_server/tests/test_session_auth.py` covering: a caller with no matching
  account (or an embargoed one - indistinguishable at this layer, corrected from the original
  task wording once implementation confirmed Django answers both identically) is admitted with no
  session credential, not refused; a tool other than signup refuses with no credential and tells
  the caller to sign up; signup grants a credential usable by the next call in the same session
  without reconnecting
- [x] 4.4 Add tests for the new tools covering every scenario in `specs/mcp-auth-tools/spec.md`:
  successful signup, duplicate email/username, weak password, blocked country, password never
  returned; reset-request identical response for an account and no account; reset-confirm success
  and the identical refusal for invalid/expired/used codes; change-my-password success, wrong
  current password, no-credential refusal, neither password ever returned
- [x] 4.5 Run `pytest` in `mcp_server/` and confirm every test passes - 72/72 passed
- [x] 4.6 Prove at least one new test can fail: temporarily revert the `NoDjangoAccountError`
  admit path to a refusal, confirm the right test goes red, then restore it - 8 tests went red,
  all restored to green

## 5. Traceability and review

- [x] 5.1 Build `traceability.md` mapping every requirement in `specs/mcp-session-auth/spec.md`'s
  MODIFIED/ADDED sections and `specs/mcp-auth-tools/spec.md` to its code and its test
- [x] 5.2 Post the proposal and both delta specs to issue #46 via `gh issue comment`
- [ ] 5.3 Run `/code-review` and record the verdict - skipped on request; user will run it
  separately to avoid the token cost of running it here
- [ ] 5.4 Fix every blocking finding, then run `/code-review` once more (verify-only) for a final
  `Ready to merge:` verdict - deferred along with 5.3
