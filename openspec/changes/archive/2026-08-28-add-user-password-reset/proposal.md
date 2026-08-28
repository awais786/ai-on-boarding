## Why

A person who forgets their password currently has no way back into their account - signup is a
one-shot event and signin only accepts the password chosen at that moment. Without a reset path,
a forgotten password is a permanently lost account.

## What Changes

- Add an endpoint that accepts an email address and begins a password reset, delivering a
  single-use reset link to that address.
- Return the same response whether or not the email is registered, so a caller cannot use the
  endpoint to discover which addresses have accounts.
- Add a second endpoint that accepts a reset code and a new password, and completes the reset.
- Serve a page at the address the link points to, so a person who follows it from their mail can
  choose a new password there rather than needing a client that can make API calls.
- Expire a reset code 30 minutes after it is issued, and retire it once it has been used.
- Leave a person's existing link working when a new reset cannot be delivered, so a mail outage
  does not take away the only way back into their account.
- Cap how often a reset can be requested for one address, so nobody can keep somebody else from
  finishing a reset by repeatedly requesting one on their behalf.
- Reject an invalid, expired, or already-used code identically, so a caller cannot tell which
  was true.
- Hold a new password to the same strength rules signup already enforces.
- Invalidate any authentication token the account already holds when its password is reset, so a
  stolen token does not survive the reset that was meant to lock the thief out.

## Capabilities

### New Capabilities

- `user-password-reset`: requesting a password reset by email, delivery of a time-limited link
  carrying a single-use reset code, completing a reset with that code and a new password,
  uniform rejection of every failure mode, and invalidation of existing authentication tokens.

### Modified Capabilities

(none)

## Impact

- Two new endpoints under `sdd_django_demo/api/`: one to request a reset, one to complete it.
- One new page, routed at the project level rather than under `api/` because the address is the
  human-facing one the mail carries. It is the project's first HTML template and its first view
  that is not part of the API surface, and it is kept out of the OpenAPI schema for that reason.
- A new stored record holding the reset code, the account it belongs to, when it was issued, and
  whether it has been used. This is the second new model in the project, after `SigninAttempt`
  in `add-user-signin`; design.md justifies it rather than letting it in silently.
- Outbound email becomes a dependency for the first time. The project constraint that it runs
  and tests with no environment variables still holds - design.md selects a delivery mechanism
  that honours it.
- No new runtime dependency. Reset codes and token invalidation both use facilities already
  present in Django and in `rest_framework.authtoken`.

### Sequencing

`add-user-signin` is planned but not yet implemented, and this change does not depend on it. The
token-invalidation requirement is written against the stored authentication token itself, not
against the signin endpoint, so it is testable before signin ships.

Two interactions are deliberately **out of scope**, to be revisited once signin exists:

- Whether a successful reset should clear an email's signin lockout.
- Whether requesting a reset should count against the signin failure counter.

Neither can be tested today, and a requirement nobody can write a failing test against is not a
requirement.
