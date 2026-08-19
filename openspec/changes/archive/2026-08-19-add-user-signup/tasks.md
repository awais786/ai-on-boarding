## 1. Serializer

- [x] 1.1 Create `SignupSerializer` in `sdd_django_demo/api/serializers.py` with `email`
  (`EmailField`) and `password` (`CharField`, write-only), both required and non-blank
- [x] 1.2 Add `validate_password_strength`: at least 8 characters, at least one letter and one
  digit
- [x] 1.3 Add `validate_email`: normalise to lowercase, reject if already registered
- [x] 1.4 Implement `create()`: `User.objects.create_user(username=email, email=email,
  password=...)` wrapped in `transaction.atomic()`, catching `IntegrityError` and converting it
  to the same field-keyed `ValidationError` the pre-check produces
- [x] 1.5 Create `AccountSerializer` output representation exposing `email` only

## 2. Endpoint

- [x] 2.1 Implement `SignupView` (`generics.CreateAPIView`) in `sdd_django_demo/api/views.py`,
  returning HTTP 200 with the output representation on success
- [x] 2.2 Add the `signup/` route to `sdd_django_demo/api/urls.py`
- [x] 2.3 Add drf-spectacular schema annotations documenting the success and rejection responses

## 3. Tests (after implementation, from the spec)

- [x] 3.1 List every requirement in `specs/user-signup/spec.md` and what a test would need to
  assert, working only from the spec
- [x] 3.2 Write `sdd_django_demo/api/test_signup.py` from that list - 14 tests covering every
  requirement, including a dedicated regression test for the concurrent-signup race
- [x] 3.3 Run `pytest` and confirm all tests pass
- [x] 3.4 Prove the race-condition test can actually fail - confirmed during development (an
  earlier version of the fix left the transaction broken, and the test caught it)

## 4. Traceability and review

- [x] 4.1 Build `traceability.md` mapping every requirement to its code and test
- [x] 4.2 Run `/code-review` - round 1 blocked on the race condition and zero tests
- [x] 4.3 Fix both blocking findings
- [x] 4.4 Run `/code-review` again (round 2, verify-only) - `Ready to merge: yes`
