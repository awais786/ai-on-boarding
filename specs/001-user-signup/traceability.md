# Traceability: User Signup

One row per requirement in [`spec.md`](./spec.md). Code and test paths are relative to
`sdd_django_demo/`.

| # | Requirement | Code | Test |
|---|---|---|---|
| FR-001 | Accept a signup submission with email and password | `api/views.py:SignupView.create` | `test_signup_creates_exactly_one_account` |
| FR-002 | Reject a submission with absent/empty email | `api/serializers.py:SignupSerializer.email` (`required=True, allow_blank=False`) | `test_signup_requires_email` |
| FR-003 | Reject a submission with absent/empty password | `api/serializers.py:SignupSerializer.password` (`required=True, allow_blank=False`) | `test_signup_requires_password` |
| FR-004 | Reject an invalid email address | `api/serializers.py:SignupSerializer.email` (`EmailField`) | `test_signup_rejects_malformed_email` |
| FR-005 | Reject an already-registered email | `api/serializers.py:validate_email` + `create` (IntegrityError fallback) | `test_signup_rejects_duplicate_email`, `test_signup_duplicate_email_race_returns_400_not_500` |
| FR-006 | Reject password shorter than 8 chars / without a letter+digit | `api/serializers.py:validate_password_strength` | `test_signup_rejects_password_shorter_than_minimum`, `test_signup_rejects_password_without_digit`, `test_signup_rejects_password_without_letter` |
| FR-007 | A valid submission creates exactly one account | `api/serializers.py:SignupSerializer.create` | `test_signup_creates_exactly_one_account` |
| FR-008 | Password stored unrecoverable | `api/serializers.py:create` (`User.objects.create_user`) | `test_signup_stores_password_hashed_not_plaintext` |
| FR-009 | Password never in any response | `api/serializers.py:AccountSerializer` (fields=['email']) | `test_signup_response_never_contains_password` |
| FR-010 | Rejection identifies the offending field | DRF's default field-keyed error rendering | `test_signup_requires_email`, `test_signup_requires_password`, `test_signup_rejects_malformed_email`, `test_signup_rejects_duplicate_email`, `test_signup_rejects_password_shorter_than_minimum` |
| FR-011 | Success returns HTTP 200 with email only | `api/views.py:SignupView.create` | `test_signup_success_returns_200_with_only_email` |
| FR-012 | Email normalised to lowercase before storage/comparison | `api/serializers.py:validate_email` | `test_signup_duplicate_email_is_case_insensitive`, `test_signup_normalises_email_to_lowercase` |

## Notes

- FR-005's traceability includes the race-condition regression test
  (`test_signup_duplicate_email_race_returns_400_not_500`), added after `/code-review` found the
  original check-then-create implementation could return an unhandled 500 under concurrent
  signups for the same email. Fix: `create()` wraps the write in `transaction.atomic()` and
  converts `IntegrityError` on the `username` unique constraint into the same field-keyed 400 the
  pre-check produces.
- Every row has at least one test; every test in `api/test_signup.py` serves at least one row
  above. No orphans in either direction.
