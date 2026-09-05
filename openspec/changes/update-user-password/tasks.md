## 1. Serializer

- [x] 1.1 Create `PasswordUpdateSerializer` in `sdd_django_demo/api/serializers.py` with
  `current_password` (`CharField`, write-only, `required=False`) and `new_password`
  (`CharField`, write-only, `required=True`, `validators=[validate_password_strength]`)
- [x] 1.2 No `validate_current_password`/cross-field check in the serializer itself - whether
  `current_password` is required, and whether it matches, depends on the target account (the
  view's job, per design.md - Decisions)

## 2. Endpoint

- [x] 2.1 Implement `PasswordUpdateView` (`generics.GenericAPIView`, `patch` method) in
  `sdd_django_demo/api/views.py`: `TokenAuthentication` + `SessionAuthentication`,
  `IsAuthenticated`, looking up the target `User` by the `<username>` URL kwarg, case-
  insensitively (`username__iexact`), 404 if none matches
- [x] 2.2 In the view, before touching the serializer: if the target is not the caller's own
  account, require `request.user.is_staff` or reject with HTTP 403 (design.md - permission check
  first)
- [x] 2.3 Validate the serializer; if the target is the caller's own account, additionally
  require `current_password` present and matching (`user.check_password(...)`), rejecting with
  a field-keyed 400 if missing or wrong
- [x] 2.4 On success: `target.set_password(new_password)`, delete the target's tokens, all inside
  one `transaction.atomic()` block (mirrors `complete_reset`'s shape per design.md), then return
  HTTP 200 with a body containing no password
- [x] 2.5 Add the `users/<str:username>/update-password/` route to `sdd_django_demo/api/urls.py`
- [x] 2.6 Add drf-spectacular schema annotations documenting the success and rejection responses
- [x] 2.7 Update `mcp_server/my_server.py`'s `update_password` tool to take `username` instead of
  `email`, and PATCH `/api/users/<username>/update-password/` directly - dropping the page-
  through-`/api/users/` lookup step (design.md/proposal.md - Impact), since the target is now
  named in the URL and no separate staff-gated id resolution is needed

## 3. Tests (after implementation, from the spec)

- [x] 3.1 List every requirement in `specs/user-password-update/spec.md` and what a test would
  need to assert, working only from the spec
- [x] 3.2 Update `sdd_django_demo/api/test_password_update.py` for the username-keyed route:
  covering missing auth, self-update with correct/incorrect/missing current password, staff
  updating another account without that account's current password, non-staff targeting another
  account, missing new password, weak new password, nonexistent target *username*, case-
  insensitive username match, response contains no password on success or rejection, old
  password stops working, new password works, pre-existing tokens invalidated on both self- and
  admin-issued updates, and that an admin's own token is unaffected by updating someone else's
  password
- [x] 3.3 Run `pytest` and confirm all tests pass (159/159 project-wide)
- [x] 3.4 Prove at least one new test can actually fail: temporarily changed the username lookup
  from `username__iexact` to `username` (exact), confirmed
  `test_password_update_matches_username_case_insensitively` went red (404 instead of 200), then
  restored `iexact` and re-ran the full suite green (159/159)

## 4. Traceability and review

- [x] 4.1 Rebuild `traceability.md` mapping every requirement in
  `specs/user-password-update/spec.md` to its (username-keyed) code and test
- [x] 4.2 Run `/code-review` and address any blocking findings (no new blocking findings on the
  username-keyed delta; the pre-existing self-service current_password brute-force nit
  resurfaced, already recorded below as non-blocking)
- [x] 4.3 Re-run `/code-review` (verify-only) until `Ready to merge: yes` - `Ready to merge: yes`

## 5. GitHub issue

- [ ] 5.1 Confirm with the user before creating/commenting on the GitHub issue for this change,
  then create it via `gh issue create` if one does not already exist, and post the proposal and
  full delta spec via `gh issue comment`
