# Traceability: Reset Password Confirmation

One row per requirement in
[`specs/user-password-reset/spec.md`](./specs/user-password-reset/spec.md) - the one modified
requirement and the five added ones. Code and test paths are relative to `sdd_django_demo/`.
Requirement identity is the requirement's name, matching the convention established by
[`add-user-signup`](../archive/2026-08-19-add-user-signup/traceability.md) (OpenSpec has no
numeric `FR-XXX` scheme).

The capability's other requirements are unchanged by this change; their rows stay in
[`add-user-password-reset`](../archive/2026-08-28-add-user-password-reset/traceability.md).

All tests live in `api/test_password_reset.py`.

| Requirement | Code | Test |
|---|---|---|
| Serve a page at the delivered link *(modified: the form now asks twice)* | `api/templates/api/password_reset.html` (second `input`, `name="confirm_password"`), `api/views.py:PasswordResetPageView` | `test_the_form_asks_for_the_new_password_twice`, `test_a_usable_link_opens_a_password_form`, `test_submitting_the_form_completes_the_reset`, `test_every_unusable_link_shows_the_same_page_and_no_form`, `test_a_weak_password_keeps_the_form_open` |
| Require the two password entries to match | `api/views.py:PasswordResetPageView.post` (`password != request.POST.get('confirm_password', '')`), `PAGE_MISMATCH`, `PasswordResetPageView.reopen` | `test_two_entries_that_differ_change_nothing`, `test_a_mismatch_keeps_the_form_open`, `test_a_mismatch_does_not_spend_the_reset_link`, `test_an_empty_second_entry_is_a_mismatch` |
| Report a mismatch before judging the password | `api/views.py:PasswordResetPageView.post` (match check placed above the `validate_password_strength` call) | `test_a_mismatch_is_reported_ahead_of_a_strength_complaint`, `test_strength_is_still_judged_once_the_entries_match` |
| Decide the link before the password | `api/views.py:PasswordResetPageView.post` (`PasswordResetCode.resolve` guard, still the first statement) | `test_a_dead_link_is_refused_rather_than_reporting_a_mismatch`, `test_an_unusable_link_offers_no_form_even_when_the_password_is_weak` |
| Never retain the confirmation entry | `api/views.py:PasswordResetPageView.post` (read, compared, never passed on), `PasswordResetPageView.reopen` (renders no submitted value), `api/templates/api/password_reset.html` (no `value=` on either input) | `test_the_confirmation_is_not_stored`, `test_neither_entry_appears_in_any_response` (3 cases: completes, mismatch, too weak) |
| Complete a reset through the API with a single password | `api/serializers.py:PasswordResetConfirmSerializer` (unchanged - `code` and `password` only), `api/views.py:PasswordResetConfirmView.post` (unchanged) | `test_the_api_completes_with_one_password_and_no_confirmation` |

## Notes

- **No change to `complete_reset`.** Both entry points still share it, so *Retire a reset code
  once it is used* and *Invalidate existing authentication tokens on reset* continue to hold
  identically for the page and the API. Verified against `git diff`.
- **No database change.** The confirmation is compared and discarded. No model field, no
  migration.
- **Failure proven, not assumed.** The mismatch and strength checks were deliberately swapped;
  `test_a_mismatch_is_reported_ahead_of_a_strength_complaint` failed with the strength message in
  place of the mismatch, then passed again once the order was restored.
- **Existing form tests migrated** to a `submit_form` helper that confirms the password by
  default, so tests about expiry, replay, and token invalidation say only what they are about.
