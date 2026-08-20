# Traceability: User Signup

One row per requirement in [`specs/user-signup/spec.md`](./specs/user-signup/spec.md) (this
change's delta — now merged into the canonical
[`openspec/specs/user-signup/spec.md`](../../specs/user-signup/spec.md)). Code and test paths
are relative to `sdd_django_demo/`.

Recreated 2026-08-20 — this file existed during the project's earlier Spec Kit phase but was not
carried over when that work was migrated into OpenSpec; see `sdd_django_demo/README.md`'s step-7
note. Requirement identity here is the requirement's name (OpenSpec has no numeric `FR-XXX`
scheme); the mapping below is otherwise unchanged from the original.

| Requirement | Code | Test |
|---|---|---|
| Accept a signup submission | `api/views.py:SignupView.create` | `test_signup_creates_exactly_one_account` |
| Reject a missing email | `api/serializers.py:SignupSerializer.email` (`required=True, allow_blank=False`) | `test_signup_requires_email` |
| Reject a missing password | `api/serializers.py:SignupSerializer.password` (`required=True, allow_blank=False`) | `test_signup_requires_password` |
| Reject an invalid email address | `api/serializers.py:SignupSerializer.email` (`EmailField`) | `test_signup_rejects_malformed_email` |
| Reject a duplicate email | `api/serializers.py:validate_email` + `create` (`IntegrityError` fallback) | `test_signup_rejects_duplicate_email`, `test_signup_duplicate_email_race_returns_400_not_500` |
| Enforce a minimum password strength | `api/serializers.py:validate_password_strength` | `test_signup_rejects_password_shorter_than_minimum`, `test_signup_rejects_password_without_digit`, `test_signup_rejects_password_without_letter` |
| Create exactly one account on a valid submission | `api/serializers.py:SignupSerializer.create` | `test_signup_creates_exactly_one_account` |
| Store the password unrecoverably | `api/serializers.py:create` (`User.objects.create_user`) | `test_signup_stores_password_hashed_not_plaintext` |
| Never return the password | `api/serializers.py:AccountSerializer` (`fields=['email']`) | `test_signup_response_never_contains_password` |
| Name the offending field on rejection | DRF's default field-keyed error rendering | `test_signup_requires_email`, `test_signup_requires_password`, `test_signup_rejects_malformed_email`, `test_signup_rejects_duplicate_email`, `test_signup_rejects_password_shorter_than_minimum` |
| Signal success with the created account's email | `api/views.py:SignupView.create` | `test_signup_success_returns_200_with_only_email` |
| Normalise email to lowercase | `api/serializers.py:validate_email` | `test_signup_duplicate_email_is_case_insensitive`, `test_signup_normalises_email_to_lowercase` |

## Notes

- "Reject a duplicate email"'s traceability includes the race-condition regression test
  (`test_signup_duplicate_email_race_returns_400_not_500`), added after `/code-review` found the
  original check-then-create implementation could return an unhandled 500 under concurrent
  signups for the same email. Fix: `create()` wraps the write in `transaction.atomic()` and
  converts `IntegrityError` on the `username` unique constraint into the same field-keyed 400 the
  pre-check produces.
- Every row has at least one test; every test in `api/test_signup.py` serves at least one row
  above. No orphans in either direction.
