# Traceability: User Password Reset

One row per requirement in [`specs/user-password-reset/spec.md`](./specs/user-password-reset/spec.md).
Code and test paths are relative to `sdd_django_demo/`. Requirement identity here is the
requirement's name, matching the convention established by
[`add-user-signup`](../archive/2026-08-19-add-user-signup/traceability.md) (OpenSpec has no
numeric `FR-XXX` scheme).

All tests live in `api/test_password_reset.py`.

| Requirement | Code | Test |
|---|---|---|
| Accept a reset request | `api/views.py:PasswordResetRequestView.post` | `test_reset_request_with_an_email_is_accepted` |
| Reject a reset request with no email | `api/serializers.py:PasswordResetRequestSerializer.email` (`required=True, allow_blank=False`) | `test_reset_request_without_an_email_names_the_email_field` |
| Answer every reset request identically | `api/views.py:RESET_REQUESTED_BODY` + the single `return` in `PasswordResetRequestView.post` | `test_registered_and_unregistered_addresses_get_identical_answers` |
| Deliver a reset code to a registered address | `api/views.py:send_reset_link`, `api/models.py:PasswordResetCode.issue_for` | `test_a_registered_address_is_sent_a_link_carrying_a_code` |
| Deliver the reset link as an absolute address | `api/views.py:build_reset_link` + `settings.RESET_LINK_BASE_URL` | `test_the_delivered_link_is_absolute`, `test_the_link_host_comes_from_the_setting_not_the_request` |
| Deliver nothing to an unregistered address | `api/views.py:PasswordResetRequestView.post` (`if user is not None`) | `test_an_unregistered_address_is_sent_nothing` |
| Leave earlier codes usable when delivery fails | `api/views.py:try_deliver_reset_link` (`transaction.atomic` around issue-and-send) | `test_a_failed_delivery_leaves_the_earlier_code_usable`, `test_a_failed_delivery_is_answered_like_a_successful_one` |
| Limit how often a reset may be requested for one address | `api/views.py:PasswordResetAddressThrottle`, `PasswordResetRequestView.throttled` + `RESET_LIMITED_BODY`, `settings.py:REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']` | `test_requests_beyond_the_limit_issue_and_send_nothing`, `test_a_flood_cannot_leave_an_address_with_no_usable_code`, `test_being_limited_does_not_reveal_whether_an_account_exists`, `test_the_limit_is_per_address_not_global`, `test_a_request_refused_by_the_limit_returns_429`, `test_two_refusals_are_identical_however_far_apart_they_are`, `test_malformed_bodies_are_not_a_way_around_the_limit` |
| Never return the reset code in a response | `api/views.py:RESET_REQUESTED_BODY` (fixed body, no code), `api/models.py:hash_reset_code` | `test_the_response_carries_neither_the_code_nor_the_link`, `test_the_stored_code_is_a_digest_rather_than_the_code` |
| Serve a page at the delivered link | `api/views.py:PasswordResetPageView`, `api/templates/api/password_reset.html`, `sdd_django_demo/urls.py` (`reset-password/<code>/`) | `test_a_usable_link_opens_a_password_form`, `test_submitting_the_form_completes_the_reset`, `test_every_unusable_link_shows_the_same_page_and_no_form`, `test_a_weak_password_keeps_the_form_open`, `test_the_link_the_mail_carries_actually_resolves` |
| Accept a reset completion | `api/views.py:PasswordResetConfirmView.post` | `test_a_completion_with_a_valid_code_is_accepted` |
| Reject a reset completion with missing fields | `api/serializers.py:PasswordResetConfirmSerializer` (`code`, `password` both `required=True, allow_blank=False`) | `test_a_completion_without_a_code_names_the_code_field`, `test_a_completion_without_a_password_names_the_password_field` |
| Complete a reset with a valid code | `api/views.py:PasswordResetConfirmView.post` (`set_password` + `save`) | `test_a_completed_reset_changes_the_password`, `test_the_previous_password_stops_working` |
| Hold a new password to the signup strength rules | `api/serializers.py:PasswordResetConfirmSerializer.password` reusing `validate_password_strength` | `test_a_password_signup_would_reject_is_refused`, `test_a_refused_weak_password_leaves_the_old_one_working` |
| Expire a reset code after 30 minutes | `api/models.py:RESET_CODE_TTL`, `PasswordResetCode.is_expired` | `test_a_code_older_than_thirty_minutes_is_refused`, `test_a_code_inside_the_window_is_accepted` |
| Retire a reset code once it is used | `api/models.py:PasswordResetCode.claim` (conditional UPDATE), spent via `api/views.py:complete_reset` | `test_a_used_code_cannot_be_replayed`, `test_the_page_cannot_be_used_twice` |
| Supersede an earlier unused code | `api/models.py:PasswordResetCode.issue_for` (bulk `update(usable=False)` before issuing) | `test_requesting_again_kills_the_earlier_code` |
| Reject every bad code identically | `api/models.py:PasswordResetCode.resolve` (collapses all four causes to `None`), `api/views.py:RESET_REFUSED_BODY` (one branch) | `test_all_four_unusable_codes_are_refused_identically` |
| Return HTTP 400 when a reset completion is refused | `api/views.py:PasswordResetConfirmView.post` (`status=400`) | `test_a_refused_completion_returns_400` |
| Invalidate existing authentication tokens on reset | `api/views.py:PasswordResetConfirmView.post` (`Token.objects.filter(user=user).delete()`) | `test_a_token_held_before_the_reset_stops_working` |
| Never return a password | `api/serializers.py:PasswordResetConfirmSerializer.password` (`write_only=True`) | `test_no_reset_response_contains_the_submitted_password` |
| Store a new password unrecoverably | `api/views.py:PasswordResetConfirmView.post` (`set_password`, Django's hasher) | `test_the_new_password_is_not_stored_as_submitted` |

## Notes

- **`resolve` is where the identical-refusal guarantee lives.** Unrecognised, expired, used and
  superseded codes all become `None` in one place, so `PasswordResetConfirmView` has a single
  refusal branch and the four cases cannot drift apart. Breaking this on purpose was confirmed to
  turn `test_all_four_unusable_codes_are_refused_identically` red while every other test stayed
  green — including the expiry test, which only asserts the status code.
- **The malformed-body tests are deliberately not mapped to a requirement.**
  `test_a_body_that_is_not_an_object_is_refused_not_raised` and
  `test_a_malformed_body_is_refused_the_same_way_on_both_endpoints` guard
  `api/views.py:PasswordResetAddressThrottle.get_cache_key`, which reads the body before any
  serializer does. They do not demonstrate *Reject a reset request with no email*: its scenario
  requires the response to name the email field, and a body that is not an object is answered
  with `non_field_errors` instead. What they protect is that such a body is answered at all
  rather than raising - the endpoint behind a limit behaving like the one without.
- **The limit's refusal carries no countdown.** The framework's default appends the wait
  remaining, rounded up, so two refusals taken at different moments differ by a second or more -
  which breaks the byte-identity *Limit how often a reset may be requested for one address*
  requires of its refusals. `PasswordResetRequestView.throttled` drops it. Removing that override
  was confirmed to turn both `test_two_refusals_are_identical_however_far_apart_they_are` and
  `test_being_limited_does_not_reveal_whether_an_account_exists` red, on `3600 seconds` against
  `2700 seconds`, while every other test stayed green.
- **The link's host is deliberately not derived from the request.** See design.md; the test that
  protects it sends a forged `Host` and asserts the delivered link is unmoved.
