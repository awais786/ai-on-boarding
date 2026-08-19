## 1. Lockout model

- [ ] 1.1 Create `SigninAttempt` model in `sdd_django_demo/api/models.py`: `email` (unique),
  `failed_count` (default 0), `last_failed_at` (nullable)
- [ ] 1.2 Generate and apply the migration

## 2. Serializer and view

- [ ] 2.1 Create `SigninSerializer` in `sdd_django_demo/api/serializers.py`: `email` and
  `password`, both required and non-blank
- [ ] 2.2 Implement the signin view: normalise the email, look up (or lazily create) its
  `SigninAttempt` row
- [ ] 2.3 If `failed_count >= 3` and within the 30-minute lockout window, reject immediately with
  the fixed 401 body - do not attempt authentication, do not modify the row
- [ ] 2.4 Otherwise authenticate via `authenticate(username=<normalised email>, password=...)`
- [ ] 2.5 On success: reset `failed_count` to 0, return HTTP 200 with `{"token":
  Token.objects.get_or_create(user=user)[0].key}`
- [ ] 2.6 On failure: update `failed_count`/`last_failed_at` per the state machine in design.md,
  return the same fixed 401 body used for lockout
- [ ] 2.7 Add the `signin/` route to `sdd_django_demo/api/urls.py`
- [ ] 2.8 Add drf-spectacular schema annotations for the success and rejection responses

## 3. Tests (after implementation, from the spec)

- [ ] 3.1 List every requirement in `specs/user-signin/spec.md` and what a test would need to
  assert, working only from the spec
- [ ] 3.2 Write `sdd_django_demo/api/test_signin.py` from that list
- [ ] 3.3 Assert the unregistered-email and wrong-password rejections are byte-identical (status
  and body), not just both 401
- [ ] 3.4 Assert lockout triggers on the 3rd failure and clears after the window
- [ ] 3.5 Run `pytest` and confirm all tests pass, including `test_signup.py`
- [ ] 3.6 Break the identical-rejection guarantee on purpose (e.g. make unregistered email return
  a distinct message) and confirm the matching test goes red, then restore

## 4. Traceability and review

- [ ] 4.1 Build `traceability.md` mapping every requirement to its code and test
- [ ] 4.2 Run `/code-review`
- [ ] 4.3 Fix any blocking findings and re-review once (two passes max) until `Ready to merge: yes`
