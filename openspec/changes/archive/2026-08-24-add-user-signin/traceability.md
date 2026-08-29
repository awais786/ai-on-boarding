# Traceability: User Signin

One row per requirement in [`specs/user-signin/spec.md`](./specs/user-signin/spec.md). Code and
test paths are relative to `sdd_django_demo/`.

| Requirement | Code | Test |
|---|---|---|
| Accept a signin submission | `api/views.py:SigninView.post` | `test_signin_succeeds_with_correct_credentials` |
| Reject a missing email | `api/serializers.py:SigninSerializer.email` (`required=True, allow_blank=False`) | `test_signin_requires_email` |
| Reject a missing password | `api/serializers.py:SigninSerializer.password` (`required=True, allow_blank=False`) | `test_signin_requires_password` |
| Authenticate against the matching account | `api/views.py:SigninView.post` (email lower-cased before `authenticate(username=...)`) | `test_signin_case_insensitive_email_match` |
| Succeed with correct credentials | `api/views.py:SigninView.post` (`authenticate` success branch) | `test_signin_succeeds_with_correct_credentials`, `test_signin_repeated_with_same_credentials_succeeds_again` |
| Signal success with an authentication token | `api/views.py:SigninView.post` (`Token.objects.get_or_create`) | `test_signin_succeeds_with_correct_credentials`, `test_signin_response_contains_only_token` |
| Reject an unregistered email | `api/views.py:SigninView.post` (`authenticate` returns `None` for no matching user) | `test_signin_rejects_unregistered_email` |
| Reject an incorrect password | `api/views.py:SigninView.post` (`authenticate` returns `None` for wrong password) | `test_signin_rejects_wrong_password` |
| Reject all failure modes identically | `api/views.py:SigninView.post` (`SIGNIN_REJECTION_BODY` returned unchanged for every failure branch) | `test_signin_unregistered_email_and_wrong_password_are_identical`, `test_signin_lockout_rejection_matches_wrong_password_rejection` |
| Return HTTP 401 on rejection | `api/views.py:SigninView.post` (`status=401` on every rejection branch) | `test_signin_rejects_unregistered_email`, `test_signin_rejects_wrong_password`, `test_signin_lockout_after_third_failure` |
| Never return the password | `api/serializers.py:SigninSerializer.password` (`write_only=True`) + `SIGNIN_REJECTION_BODY`/`TokenSerializer` never include it | `test_signin_never_returns_password` |
| Lock an email out after repeated failures | `api/models.py:SigninAttempt` + `api/views.py:SigninView.post` (lockout check reads the row; the failure-count update is a single atomic `UPDATE` via `Case`/`When`/`F`, computed and written server-side in one statement so concurrent failures against the same email can't race the counter - correct on any backend, including this project's SQLite, where `select_for_update()` would silently be a no-op) | `test_signin_lockout_after_third_failure`, `test_signin_lockout_expires_after_window` |
| Reset the failure count on success | `api/views.py:SigninView.post` (`attempt.failed_count = 0` on success) | `test_signin_success_resets_failure_count` |

## Notes

- `/code-review`'s first pass found the `SigninAttempt.failed_count` read-modify-write could lose
  updates under concurrent failed attempts against the same email (no row lock), undermining the
  lockout requirement. First fix attempt used `transaction.atomic()` + `select_for_update()`; the
  follow-up review pass found that ineffective, since Django's sqlite3 backend never sets
  `has_select_for_update` (confirmed in the installed `django/db/backends/base/features.py`), so
  the "lock" compiled to a plain `SELECT` and the race was still present. Replaced with a single
  atomic `UPDATE` (`Case`/`When`/`F`) that computes and writes the counter in one server-side
  statement, which is race-free regardless of backend since there's no separate application-level
  read-then-write round trip for the counter itself.
- The follow-up review pass also raised a second, unconfirmed finding: that concurrent
  `get_or_create(email=email)` calls for a brand-new email could raise an uncaught
  `IntegrityError`. Verified against the installed Django source
  (`QuerySet.get_or_create`/`_create_object_from_params`) that this is a false positive - Django's
  `get_or_create()` already catches `IntegrityError` internally and retries the lookup, returning
  the existing row. No code change made for this one.
- A separate, non-blocking nit from the first pass (an unconditional re-save of
  `failed_count = 0` on an already-zero success) was superseded by the rewrite above, which
  writes success as a single unconditional `.update(failed_count=0)` - equally cheap, no
  conditional needed.
- "Reject all failure modes identically" additionally covers the guarantee holding across
  *lockout* specifically (not just unregistered-email vs. wrong-password), via
  `test_signin_lockout_rejection_matches_wrong_password_rejection`, which compares a locked-out
  account's rejection against a wrong-password rejection on a separate, unlocked account.
- The identical-rejection guarantee was verified to actually break a test if violated: a
  temporary change that made the unregistered-email branch return a distinct body turned
  `test_signin_unregistered_email_and_wrong_password_are_identical` red before being reverted (no
  net code change).
- Every row has at least one test; every test in `api/test_signin.py` serves at least one row
  above. No orphans in either direction.
