# Traceability: MCP Google Authentication

One row per requirement in [`specs/google-signin/spec.md`](./specs/google-signin/spec.md). Code
and test paths are relative to `sdd_django_demo/`.

| Requirement | Code | Test |
|---|---|---|
| Accept a Google access token submission | `api/serializers.py:GoogleSigninSerializer.access_token` (`required=True, allow_blank=False`) | `test_google_signin_requires_access_token` |
| Verify the token with Google before trusting it | `api/google_auth.py:verify_google_access_token` + `api/views.py:GoogleSigninView.post` | `test_google_signin_rejects_invalid_or_expired_token` |
| Reject a token issued to an unrecognised audience | `api/views.py:GoogleSigninView.post` (`claims['aud']` against `settings.GOOGLE_OAUTH_ALLOWED_CLIENT_IDS`) | `test_google_signin_rejects_unrecognised_audience`, `test_google_signin_succeeds_with_audience_on_the_allowlist` |
| Reject an unverified email | `api/views.py:GoogleSigninView.post` (`claims['email_verified']` check) | `test_google_signin_rejects_unverified_email` |
| Reject a token outside the configured domain allowlist | `api/views.py:GoogleSigninView.post` (`claims['hd']` against `settings.GOOGLE_OAUTH_ALLOWED_DOMAINS`, skipped when that setting is empty) | `test_google_signin_rejects_domain_not_on_configured_allowlist`, `test_google_signin_succeeds_with_domain_on_configured_allowlist`, `test_google_signin_succeeds_with_no_domain_allowlist_configured_and_hd_present`, `test_google_signin_succeeds_with_no_domain_allowlist_configured_and_hd_absent` |
| Map a verified Google identity to its Django account | `api/models.py:GoogleIdentity`, `api/views.py:GoogleSigninView.post` (lookup by `google_sub`) | `test_google_signin_previously_linked_identity_authenticates_after_email_change` |
| Reject a verified identity with no linked or matching account | `api/views.py:GoogleSigninView.post` (no `GoogleIdentity` and no `User.objects.filter(email__iexact=...)` match; a missing `email` claim is treated as unmatched rather than falling back to `''`, and a missing `sub` claim is rejected before any lookup) | `test_google_signin_rejects_identity_with_no_linked_or_matching_account`, `test_google_signin_rejects_missing_email_even_if_an_account_has_a_blank_email`, `test_google_signin_rejects_claims_with_no_sub` |
| First successful authentication links the identity | `api/views.py:GoogleSigninView.post` (`GoogleIdentity.objects.create` on first email match) | `test_google_signin_first_time_login_links_identity_to_matching_account` |
| Reject an embargoed account | `api/views.py:GoogleSigninView.post` (`is_user_embargoed`, reused from `embargo.rules`, checked before the identity link is created) | `test_google_signin_rejects_embargoed_mapped_account`, `test_google_signin_does_not_link_identity_on_a_rejected_embargoed_first_login` |
| Issue the existing application token on success | `api/views.py:GoogleSigninView.post` (`Token.objects.get_or_create`, `TokenSerializer` shape) | `test_google_signin_succeeds_and_issues_the_existing_token`, `test_google_signin_response_shape_is_token_only` |

## Notes

- "Reject a token outside the configured domain allowlist" required resolving a design gap found
  during implementation: Google's tokeninfo endpoint could not be confirmed to return `hd` for an
  access token (as opposed to an ID token). `verify_google_access_token` now calls both tokeninfo
  (for `aud`) and Google's userinfo endpoint (for `sub`/`email`/`email_verified`/`hd`) - see
  design.md's "Google token verification" decision. `api/test_google_auth.py` exercises this
  function's real HTTP/parsing logic directly (mocking `urllib.request.urlopen`, not the whole
  function), rather than every call site mocking the function away - `/code-review` (round 1)
  flagged that the security-sensitive verification path was otherwise never actually exercised.
- `/code-review` (round 1, 9 confirmed findings) also caught: `GoogleIdentity` being persisted
  before the embargo check ran (fixed - reordered, with a dedicated regression test), the
  first-time email lookup having no `.order_by('pk')` (fixed - matches `PasswordResetRequestView`'s
  identical, already-documented convention), an uncaught `IntegrityError` on a concurrent
  first-time link race (fixed - caught and re-resolved, with a regression test simulating the
  race), and `google_auth.py`'s except clause missing `http.client.HTTPException`/`OSError` plus
  design.md's claimed logging never being implemented (both fixed).
- Two round-1 findings were recorded as nits, not fixed, per the review contract (neither cites a
  requirement, a named test, or a documented convention this change violates): the MCP server's
  module-level `_token` cache racing across concurrently-authenticated callers is a pre-existing
  architectural pattern this change reuses rather than introduces; `mcp_server/my_client.py`
  (a demo script, not a "tool") now needs a Google login it doesn't perform, which is outside
  tasks.md's scope and not silently fixed without being asked.
- Round 2 (follow-up pass, 5 findings) caught: an empty/missing `email` claim falling back to
  `''` and matching a blank-email account instead of being rejected (fixed - violated the "no
  linked or matching account" requirement directly); a missing `sub` claim misattributed to the
  concurrent-creation race and silently swallowed (fixed - now rejected up front, logged as an
  anomaly); a duplicated `GoogleIdentity` lookup query, extracted to `_find_google_identity`
  (fixed); and no test for the MCP tool's token-non-exposure property, addressed with
  `mcp_server/test_google_signin_tool.py` - stdlib `unittest` only, so no new dependency was
  needed to close this gap (mirrors and closes the "no MCP-level test suite" note above, for
  this one property). One round-2 finding was recorded as a nit: `GoogleSigninView` has no
  throttle - a real operational concern, but not cited to any requirement/test/convention, and
  choosing a throttle key is an undecided design question outside this change's proposal.
- Per `openspec/config.yaml`'s two-pass cap (an initial pass and one follow-up, never a third),
  this document's own analysis of round 2's findings is the final verdict rather than a third
  automated `/code-review` invocation. Full suite: 183 passed, no regressions.
  **Ready to merge: yes**
- Every row has at least one test; every test in `api/test_google_signin.py`,
  `api/test_google_auth.py`, and `mcp_server/test_google_signin_tool.py` serves at least one row
  above or the MCP-side non-exposure property noted below. No orphans in either direction.
- MCP-side changes (`mcp_server/my_server.py`'s `GoogleProvider` wiring and the `google_signin`
  tool) are covered by proposal.md/design.md's Impact but have no corresponding spec requirement,
  matching this project's existing convention (see `update-user-password`'s proposal: MCP tool
  changes are Impact, not a separate capability) - there is no MCP-level test suite in this repo
  for any tool, new or existing, to add tests to.
