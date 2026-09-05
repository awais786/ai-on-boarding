## Why

There is currently no way to change a password while authenticated - the only path today is the
password-reset flow, which starts from an unauthenticated request and a mailed code. An admin
has no way to set a password on another account (e.g. to help a locked-out or embargoed user
without going through email), and a signed-in user has no way to change their own password
without going through the reset flow.

## What Changes

- Add an endpoint that updates a user's password while authenticated.
- A staff/admin caller may update any account's password, given only the new password.
- A non-staff caller may update only their own password, and must additionally supply their
  current password to confirm identity.
- A non-staff caller attempting to update a different account's password is rejected.
- The new password is held to the same strength rule signup already applies.
- A successful update invalidates every authentication token the account already holds, matching
  the existing password-reset behaviour.

## Capabilities

### New Capabilities
- `user-password-update`: lets an authenticated caller change a password - their own (with
  current-password confirmation) if not staff, or any account's (without needing that account's
  current password) if staff.

### Modified Capabilities
(none - this does not change the behaviour of signup, signin, or password-reset)

## Impact

- New API endpoint under `sdd_django_demo/api/` (new view, serializer, and URL route).
- Reuses the existing password strength validator and the existing token-invalidation approach
  from password reset - no new dependency.
- No schema/model changes.
- `mcp_server/my_server.py`'s `update_password` tool now takes `username` and PATCHes
  `/api/users/<username>/update-password/` directly, dropping its staff-gated page-through-
  `/api/users/` lookup step (previously the only way it resolved an account id from an email).
