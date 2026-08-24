## Why

An account that can be created but never used to sign in delivers no value. Signin is the second
half of the entry point `user-signup` opened.

## What Changes

- Add a signin endpoint accepting an email address and a password, returning an authentication
  token on success.
- Reject an unregistered email and a wrong password identically, so a caller cannot tell which
  was true (prevents email enumeration).
- Lock an email out for 30 minutes after 3 failed attempts within a 5-minute window.

## Capabilities

### New Capabilities

- `user-signin`: authentication via email and password, token issuance, identical rejection for
  every failure mode, and lockout after repeated failures.

### Modified Capabilities

(none)

## Impact

- New endpoint `POST /api/signin/` in `sdd_django_demo/api/`.
- New model `SigninAttempt` to track lockout state - the first departure from `user-signup`'s
  "no new model" precedent, justified in design.md.
- No new runtime dependency - uses `rest_framework.authtoken`, bundled with DRF and already
  installed.
