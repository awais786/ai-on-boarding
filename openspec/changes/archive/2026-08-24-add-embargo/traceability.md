# Traceability: Embargo

One row per requirement across `specs/embargo/spec.md` and this change's `user-signup` and
`user-signin` deltas. Code and test paths are relative to `sdd_django_demo/`.

## `embargo` (new capability)

| Requirement | Code | Test |
|---|---|---|
| Maintain a configurable list of blocked countries | `embargo/models.py:BlockedCountry` + `embargo/rules.py:is_blocked` | `test_unlisted_country_is_allowed`, `test_listed_country_is_blocked` |
| Match a country case-insensitively | `embargo/rules.py:is_blocked` (`country__iexact`) | `test_country_matched_case_insensitively` |
| Evaluate checks against the list's current state | `embargo/rules.py:is_blocked` (queries the table fresh on every call, no caching) | `test_later_addition_takes_effect`, `test_later_removal_takes_effect` |

## `user-signup` (delta)

| Requirement | Code | Test |
|---|---|---|
| Accept a signup submission (MODIFIED - now includes country) | `api/serializers.py:SignupSerializer.country` | `test_signup_allows_unblocked_country` |
| Reject a missing country | `api/serializers.py:SignupSerializer.country` (`required=True, allow_blank=False`) | `test_signup_requires_country` |
| Reject a submission from a blocked country | `api/serializers.py:SignupSerializer.validate_country` (`embargo.rules.is_blocked`) | `test_signup_rejects_blocked_country` |

## `user-signin` (delta)

| Requirement | Code | Test |
|---|---|---|
| Reject all failure modes identically (MODIFIED - now four reasons) | `api/views.py:SigninView.post` (embargo branch returns the same `SIGNIN_REJECTION_BODY` as every other rejection) | `test_signin_embargo_rejection_matches_wrong_password_rejection` |
| Reject signin for an embargoed account | `api/views.py:SigninView.post` (post-authentication check against `embargo.models.AccountCountry` + `embargo.rules.is_blocked`) | `test_signin_rejects_embargoed_account`, `test_signin_country_blocked_after_signup_locks_out_next_attempt`, `test_signin_country_unblocked_after_being_blocked_allows_signin` |

## Notes

- `/code-review` raised two findings, both on pre-existing signin code this change does not
  touch: `SigninSerializer.email` has no format/length bound, and the success-path counter reset
  re-queries instead of reusing the already-fetched `SigninAttempt` row. Neither cites a
  requirement id, a named failing test, or a documented convention, so both are non-blocking nits
  per the review contract - recorded here, not fixed as part of this change.
- "Reject all failure modes identically"'s widened guarantee was verified to actually break a
  test if violated: a temporary change that made the embargo-rejection branch return a distinct
  body turned `test_signin_embargo_rejection_matches_wrong_password_rejection` red before being
  reverted (no net code change).
- `test_signin_embargo_rejection_does_not_increment_failure_count` covers a design decision (the
  embargo branch never touches `SigninAttempt`) rather than a spec requirement by itself, but
  protects the "does not touch the lockout counter" property `design.md` calls out explicitly.
- Every row has at least one test; every new test in `embargo/test_rules.py`,
  `api/test_signup.py`, and `api/test_signin.py` serves at least one row above. No orphans in
  either direction.
