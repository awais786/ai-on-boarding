# Traceability: Update User Password

One row per requirement in
[`specs/user-password-update/spec.md`](./specs/user-password-update/spec.md). Code and test
paths are relative to `sdd_django_demo/`.

| Requirement | Code | Test |
|---|---|---|
| Require authentication | `api/views.py:PasswordUpdateView` (`authentication_classes = [TokenAuthentication, SessionAuthentication]`, `permission_classes = [IsAuthenticated]`) | `test_password_update_rejects_unauthenticated_request` |
| Identify the target account | `api/views.py:PasswordUpdateView.patch` (`User.objects.filter(username__iexact=kwargs['username']).order_by('pk').first()`, 404 if None) + `api/urls.py` (`users/<str:username>/update-password/`) | `test_password_update_rejects_nonexistent_target`, `test_password_update_allows_staff_to_target_another_account`, `test_password_update_matches_username_case_insensitively` |
| A caller may update their own password | `api/views.py:PasswordUpdateView.patch` (`is_self = target.pk == request.user.pk`) | `test_password_update_self_service_succeeds_with_correct_current_password` |
| A non-staff caller may not update another account's password | `api/views.py:PasswordUpdateView.patch` (403 when `not is_self and not request.user.is_staff`) | `test_password_update_rejects_non_staff_targeting_another_account` |
| A staff caller may update any account's password | `api/views.py:PasswordUpdateView.patch` (permission check allows `is_staff`) | `test_password_update_allows_staff_to_target_another_account` |
| Self-service update requires the current password | `api/views.py:PasswordUpdateView.patch` (`current_password` required + `target.check_password(...)` when `is_self`, regardless of `is_staff`) | `test_password_update_self_service_requires_current_password_field`, `test_password_update_self_service_rejects_incorrect_current_password`, `test_password_update_self_service_succeeds_with_correct_current_password`, `test_password_update_staff_targeting_own_account_requires_current_password`, `test_password_update_staff_targeting_own_account_succeeds_with_correct_current_password` |
| An admin-issued update does not require the target's current password | `api/views.py:PasswordUpdateView.patch` (current-password check skipped when `not is_self`) | `test_password_update_admin_issued_update_does_not_require_current_password` |
| Reject a request with no new password | `api/serializers.py:PasswordUpdateSerializer.new_password` (`required=True`) | `test_password_update_rejects_missing_new_password` |
| Hold the new password to the signup strength rule | `api/serializers.py:PasswordUpdateSerializer.new_password` (`validators=[validate_password_strength]`) | `test_password_update_rejects_weak_new_password` |
| Signal success with HTTP 200 and no body content about the password | `api/views.py:PasswordUpdateView.patch` (returns `PASSWORD_UPDATE_COMPLETED_BODY`, status 200) | `test_password_update_success_response_contains_no_password` |
| Never return a password | `api/views.py:PasswordUpdateView.patch` (no submitted or stored password ever placed in a `Response`) | `test_password_update_success_response_contains_no_password`, `test_password_update_rejected_response_contains_no_password` |
| The account authenticates with the new password | `api/views.py:PasswordUpdateView.patch` (`target.set_password(...)`, `target.save(...)`) | `test_password_update_new_password_works_old_does_not` |
| Invalidate existing authentication tokens on update | `api/views.py:PasswordUpdateView.patch` (`Token.objects.filter(user=target).delete()` inside the same `transaction.atomic()` block) | `test_password_update_invalidates_existing_tokens_on_self_update`, `test_password_update_invalidates_target_tokens_on_admin_update_but_not_admins_own` |

## Notes

- `/code-review` round 1 found two blocking issues, both fixed: (1)
  `PASSWORD_UPDATE_FORBIDDEN_BODY` was passed to `Response()` without the `dict(...)` copy every
  other body constant in `views.py` uses, aliasing the module-level dict to `response.data` -
  fixed by wrapping it like the others. (2) No test exercised a staff caller updating their own
  account (`is_self=True, is_staff=True`) - the exact case design.md's Risks/Trade-offs names as
  the risk this feature's design is meant to guard against - added
  `test_password_update_staff_targeting_own_account_requires_current_password` and
  `test_password_update_staff_targeting_own_account_succeeds_with_correct_current_password`.
- Two non-blocking nits were also raised (no requirement or test cites either, so neither blocks
  merge per the review contract): the 404-before-403 check ordering lets an authenticated
  non-staff caller distinguish an existing account from a nonexistent one by id; and there is no
  throttle on repeated `current_password` guesses, unlike `SigninView`'s lockout for the same
  threat model. Recorded here, not implemented.
- `/code-review` round 2 (verify-only, after fixing round 1's two blocking findings and renaming
  the route to `update-password/`) re-surfaced the same two nits above and found nothing new -
  `Ready to merge: yes`.
- Verified `test_password_update_rejects_non_staff_targeting_another_account` can actually fail:
  temporarily disabled the permission check in `PasswordUpdateView.patch` (the `if not is_self
  and not request.user.is_staff: return ... 403` branch became unreachable), reran the test and
  saw it fail with HTTP 200 instead of 403, then restored the check and reran the full suite
  green (156/156).
- Every row has at least one test; every test in `api/test_password_update.py` serves at least
  one row above. No orphans in either direction.
- The route and lookup were later revised from `PATCH /api/users/<id>/update-password/` (numeric
  id) to `PATCH /api/users/<username>/update-password/` (case-insensitive username), per the
  user's request. `mcp_server/my_server.py`'s `update_password` tool was updated to match: it now
  takes `username` and PATCHes the endpoint directly, no longer paging through the staff-only
  `/api/users/` listing to resolve an id first. Added
  `test_password_update_matches_username_case_insensitively` and confirmed it can fail
  (temporarily swapped `username__iexact` for an exact match, saw the test go 404 instead of 200,
  restored it, reran the full suite green - 159/159). No other requirement or test changed.
- `/code-review` re-run after the username-keyed delta found no new blocking findings; it
  resurfaced the same self-service `current_password` brute-force nit noted above (no lockout on
  repeated guesses, unlike `SigninView`) - still non-blocking, no requirement/test/convention
  cites it - `Ready to merge: yes`.
