## 1. Signup: add a real username field

- [x] 1.1 Update `SignupSerializer` in `sdd_django_demo/api/serializers.py`: add a `username`
  field, required and non-blank, validated as 3-30 characters of letters, digits, or underscores
- [x] 1.2 In `validate_username`: normalise to lowercase; reject if a `User` with that username
  already exists (no cross-check against email needed - the username format rule already makes
  the two identifier spaces disjoint, see design.md)
- [x] 1.3 (superseded by 1.2's note - no separate email/username cross-check)
- [x] 1.4 Update `create()` to pass the submitted (normalised) username into
  `User.objects.create_user(username=..., email=..., password=...)` instead of deriving it from
  email; keep the existing `IntegrityError` catch for the concurrent-duplicate race, extended to
  name whichever field (`email` or `username`) actually collided
- [x] 1.5 Update `AccountSerializer.Meta.fields` to include `username` alongside `email`
- [x] 1.6 Add a `post_migrate` signal handler in `sdd_django_demo/api/apps.py`
  (`ApiConfig.ready()`) that runs `CREATE UNIQUE INDEX IF NOT EXISTS` on `auth_user.email`, to
  restore the DB-level race protection for duplicate emails that the old `username == email`
  coupling provided by accident - see design.md for why a migration was tried and rejected in
  favour of this. Run `migrate` to confirm the handler fires and the index is created.

## 2. Lockout model

- [x] 2.1 Create `SigninAttempt` model in `sdd_django_demo/api/models.py`: `email_or_username`
  (unique), `failed_count` (default 0), `last_failed_at` (nullable)
- [x] 2.2 Generate and apply the migration

## 3. Serializer and view

- [x] 3.1 Create `SigninSerializer` in `sdd_django_demo/api/serializers.py`: `email_or_username`
  and `password`, both required and non-blank
- [x] 3.2 Implement the signin view: normalise the submitted `email_or_username`, resolve the
  candidate account via `User.objects.filter(Q(email=email_or_username) |
  Q(username=email_or_username)).first()`, then look up (or lazily create) the `SigninAttempt`
  row keyed on the candidate's canonical email if resolved, or on the raw submitted value if not
  - see design.md (keying on the raw submitted value alone let an attacker evade lockout by
  alternating between an account's email and username)
- [x] 3.3 If `failed_count >= 3` and within the 30-minute lockout window, reject immediately with
  the fixed 401 body - do not attempt authentication, do not modify the row
- [x] 3.4 Otherwise, if a candidate account was resolved, call `authenticate(username=<that
  account's username>, password=...)`; if no candidate was found, treat it as a failed
  authentication and proceed to the same rejection path as a wrong password
- [x] 3.5 On success: reset `failed_count` to 0, return HTTP 200 with `{"token":
  Token.objects.get_or_create(user=user)[0].key}`
- [x] 3.6 On failure: update `failed_count`/`last_failed_at` per the state machine in design.md,
  return the same fixed 401 body used for lockout. Wrap the read-check-update of `SigninAttempt`
  in `transaction.atomic()` with `select_for_update()` to avoid a lost-update race under
  concurrent requests against the same account - see design.md.
- [x] 3.7 Add the `signin/` route to `sdd_django_demo/api/urls.py`
- [x] 3.8 Add drf-spectacular schema annotations for the success and rejection responses

## 4. Tests (after implementation, from the spec)

- [x] 4.1 List every requirement in `specs/user-signup/spec.md`'s delta and
  `specs/user-signin/spec.md`, and what a test would need to assert, working only from the specs
- [x] 4.2 Extend `sdd_django_demo/api/test_signup.py` with the new username requirements: missing
  username, format validation, duplicate username (including the concurrent-race scenario),
  response shape includes username
- [x] 4.3 Write `sdd_django_demo/api/test_signin.py` from the signin requirement list
- [x] 4.4 Assert signin succeeds both by email and by username, each case-insensitively
- [x] 4.5 Assert the unregistered-email-or-username and wrong-password rejections are
  byte-identical (status and body), not just both 401
- [x] 4.6 Assert lockout triggers on the 3rd failure, that failures split across both email and
  username for the same account still count toward the same lockout (not just failures repeated
  in one form), and that lockout clears after the window
- [x] 4.7 Run `pytest` and confirm all tests pass, including the existing signup tests
- [x] 4.8 Break the identical-rejection guarantee on purpose (e.g. make unregistered
  email-or-username return a distinct message) and confirm the matching test goes red, then
  restore

## 5. Traceability and review

- [x] 5.1 Build `traceability.md` mapping every requirement (signup delta and signin) to its code
  and test
- [x] 5.2 Run `/code-review`
- [x] 5.3 Fix findings from both review passes (initial pass: lockout evasion via email/username
  switching, fixed; follow-up pass: missing `max_length` on `SigninSerializer.email_or_username`,
  fixed; unlocked `SigninAttempt` read-modify-write, fixed with `select_for_update()`; collision
  risk from accounts created outside `SignupSerializer`, documented as an accepted risk in
  design.md rather than fixed - out of this change's scope, see design.md). Both review passes
  used per the project's two-pass limit.
- [x] 5.4 Renamed the `identifier` keyword to `email_or_username` throughout signin's request
  field, the `SigninAttempt` model field, and all internal variable names, per user request -
  updated code, tests, and every planning artifact (spec, design, traceability) for consistency.
