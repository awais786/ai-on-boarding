# Traceability: User Signin (and the User Signup username delta)

One row per requirement in this change's two delta specs:
[`specs/user-signup/spec.md`](./specs/user-signup/spec.md) (MODIFIED/ADDED requirements on the
already-shipped `user-signup` capability) and [`specs/user-signin/spec.md`](./specs/user-signin/spec.md)
(the new `user-signin` capability). Code and test paths are relative to `sdd_django_demo/`.

## user-signup delta

| Requirement | Code | Test |
|---|---|---|
| Accept a signup submission (MODIFIED - adds username) | `api/serializers.py:SignupSerializer` (`email`, `username`, `password` fields) | `test_signup_creates_exactly_one_account`, `test_signup_success_returns_200_with_email_and_username` |
| Signal success with the created account's email (MODIFIED - adds username) | `api/views.py:SignupView.create` + `api/serializers.py:AccountSerializer` (`fields=['email','username']`) | `test_signup_success_returns_200_with_email_and_username` |
| Reject a missing username | `api/serializers.py:SignupSerializer.username` (`required=True, allow_blank=False`) | `test_signup_requires_username` |
| Enforce a username format | `api/serializers.py:validate_username_format`, `USERNAME_RE`, `min_length`/`max_length` | `test_signup_rejects_username_too_short`, `test_signup_rejects_username_too_long`, `test_signup_rejects_username_with_disallowed_character` |
| Reject a duplicate username | `api/serializers.py:validate_username` + `create` (`IntegrityError` fallback) | `test_signup_rejects_duplicate_username`, `test_signup_duplicate_username_race_returns_400_not_500` |
| Normalise username to lowercase | `api/serializers.py:validate_username` | `test_signup_duplicate_username_is_case_insensitive`, `test_signup_normalises_username_to_lowercase` |

## user-signin

| Requirement | Code | Test |
|---|---|---|
| Accept a signin submission | `api/serializers.py:SigninSerializer` (`email_or_username`, `password`) | `test_signin_succeeds_by_email` |
| Reject a missing email or username | `api/serializers.py:SigninSerializer.email_or_username` + `api/views.py:SigninView.post` (field-named 401, not DRF's default 400 - see design.md) | `test_signin_requires_email_or_username` |
| Reject a missing password | `api/serializers.py:SigninSerializer.password` + `api/views.py:SigninView.post` | `test_signin_requires_password` |
| Authenticate against the matching account | `api/views.py:SigninView.post` (`Q(email=email_or_username) \| Q(username=email_or_username)` lookup, then `authenticate()`) | `test_signin_succeeds_by_email`, `test_signin_succeeds_by_username`, `test_signin_email_match_is_case_insensitive`, `test_signin_username_match_is_case_insensitive` |
| Succeed with correct credentials | `api/views.py:SigninView.post` | `test_signin_succeeds_by_email`, `test_signin_repeated_signin_succeeds_again` |
| Signal success with an authentication token | `api/views.py:SigninView.post` (`Token.objects.get_or_create`) | `test_signin_response_shape_is_token_only` |
| Reject an unregistered email or username | `api/views.py:SigninView.post` (`candidate is None` branch) | `test_signin_rejects_unregistered_email_or_username` |
| Reject an incorrect password | `api/views.py:SigninView.post` (`authenticate()` returns `None`) | `test_signin_rejects_wrong_password` |
| Reject all failure modes identically | `api/views.py:SigninView.post` (`REJECTED_RESPONSE` constant shared by lockout, unregistered, and wrong-password branches) | `test_signin_unregistered_email_or_username_and_wrong_password_are_identical`, `test_signin_lockout_matches_wrong_password_response` |
| Return HTTP 401 on rejection | `api/views.py:SigninView.post` (every rejection branch returns `status=401`) | `test_signin_requires_email_or_username`, `test_signin_rejects_unregistered_email_or_username`, `test_signin_rejects_wrong_password`, `test_signin_locks_out_after_third_failure` |
| Never return the password | `api/serializers.py:SigninSerializer.password` (`write_only=True`) | `test_signin_response_never_contains_password` |
| Lock an account out after repeated failures | `api/models.py:SigninAttempt` + `api/views.py:SigninView.post` (`MAX_FAILURES`, `FAILURE_WINDOW`, `LOCKOUT_DURATION`; attempt keyed on the resolved account's canonical email, or the raw submitted value if unresolved - see design.md) | `test_signin_locks_out_after_third_failure`, `test_signin_lockout_expires_after_30_minutes`, `test_signin_lockout_applies_regardless_of_email_or_username_form` |
| Reset the failure count on success | `api/views.py:SigninView.post` (`attempt.failed_count = 0` on success) | `test_signin_success_resets_failure_count` |

## Notes

- "Lock an account out after repeated failures" was fixed after `/code-review`'s first pass: the
  initial implementation keyed `SigninAttempt` purely on the raw submitted string, which let an
  attacker evade lockout by alternating between an account's email and username (3 failures via
  one form, then 3 more via the other, indefinitely). Fixed by resolving the candidate account
  first and keying the attempt row on its canonical email when resolved; unresolved values still
  get their own per-string row. See design.md and
  `test_signin_lockout_applies_regardless_of_email_or_username_form`, which now actually
  exercises mixed email/username attempts against one account (the original version of this test
  was a byte-identical copy of `test_signin_locks_out_after_third_failure` and didn't test what
  its name claimed).
- "Reject a duplicate email" (unmodified, already-shipped `user-signup` requirement) needed a
  fix alongside this change: giving `username` an independent value broke the DB-level race
  protection that `username == email` used to provide by accident. Fixed by a `post_migrate`
  signal handler in `api/apps.py` adding a real unique index on `auth_user.email` - see
  design.md for why a migration-based approach was tried first and rejected (empirically
  unreliable under this project's test runner). No dedicated regression test for this specific
  race exists yet in `test_signup.py`, matching the existing `test_signup_duplicate_email_race_returns_400_not_500`
  test's coverage, which already exercises the "pre-check bypassed, DB constraint catches it"
  path end to end and passes with the new index in place.
- A second `/code-review` pass (the project's allowed follow-up) found two more issues, both
  fixed: `SigninSerializer.email_or_username` had no `max_length`, risking an unhandled DB error
  on backends that enforce column length (SQLite, used here, does not); and the `SigninAttempt`
  read-modify-write had no locking, letting concurrent requests undercount failures. Fixed with
  `select_for_update()` inside `transaction.atomic()` in `api/views.py:SigninView.post` - see
  design.md for why no dedicated concurrency test was added (SQLite has no row-level locking, so
  a thread-based test against it would be flaky rather than meaningful).
- That same pass also noted the "username and email can never collide" reasoning only holds for
  accounts created through `SignupSerializer`, not for accounts created via `createsuperuser` or
  similar. Documented as an accepted risk in design.md, not fixed - closing it fully is outside
  what this change's specs (signup and signin) govern.
- Per user request, the `identifier` keyword was renamed to `email_or_username` throughout: the
  signin JSON request field, the `SigninAttempt` model field (folded into migration
  `0001_signinattempt` rather than carried as a separate rename migration, since this model was
  never shipped), all internal variable names, and every planning artifact's wording.
- Every row has at least one test; every test in `test_signup.py` and `test_signin.py` serves at
  least one row above. No orphans in either direction.
