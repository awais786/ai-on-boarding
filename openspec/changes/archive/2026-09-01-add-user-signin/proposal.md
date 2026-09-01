## Why

An account that can be created but never used to sign in delivers no value. Signin is the second
half of the entry point `user-signup` opened. Letting people sign in with a distinct username, in
addition to email, is a common expectation - this version adds it up front, before either
capability ships.

## What Changes

- Give signup a real, independently-chosen `username` field (3-30 characters, alphanumeric plus
  underscore), distinct from email, unique, and cross-checked so it can never collide with
  another account's email (or an email with another account's username).
- Add a signin endpoint accepting an email or username and a password, returning an
  authentication token on success.
- Reject an unregistered email or username and a wrong password identically, so a caller cannot
  tell which was true (prevents account enumeration).
- Lock an account out for 30 minutes after 3 failed attempts within a 5-minute window.

## Capabilities

### New Capabilities

- `user-signin`: authentication via email or username and password, token issuance, identical
  rejection for every failure mode, and lockout after repeated failures.

### Modified Capabilities

- `user-signup`: adds a required, unique `username` field alongside email - format-validated,
  normalised to lowercase, and cross-checked against every existing account's email so the two
  identifier spaces can never overlap.

## Impact

- New endpoint `POST /api/signin/` in `sdd_django_demo/api/`.
- Modified endpoint `POST /api/signup/` (and its response, and `AccountSerializer`) to accept
  and return `username`.
- New model `SigninAttempt` to track lockout state - the first departure from `user-signup`'s
  "no new model" precedent, justified in design.md.
- No schema change for `username` itself - reuses Django's existing `User.username` column - but
  a `post_migrate` signal handler adds a raw-SQL unique index on `auth_user.email`, restoring
  race protection that the old `username == email` coupling provided by accident (see
  design.md).
- No new runtime dependency - uses `rest_framework.authtoken`, bundled with DRF and already
  installed.
