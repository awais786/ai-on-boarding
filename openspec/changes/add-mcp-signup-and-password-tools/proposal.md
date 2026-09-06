## Why

Issue #46 asks the MCP server to expose signup, change password, and forgot/reset password as
tools alongside the reporting tools it already has (signin is deliberately excluded - Google
sign-in plus the existing token exchange already serves as the sign-in step for reaching MCP at
all, so a separate signin tool would be redundant). Today, reaching any tool at all requires an
existing Django account: the server exchanges the caller's Google identity for a Django API
token before any tool call is allowed through, and a caller with no matching account is refused
at that point. That refusal happens before signup could ever run, so a caller without an account
today has no way to create one through this server.

## What Changes

- A caller whose Google identity has no matching Django account is let through to the MCP
  session instead of being refused outright; every tool other than the new signup tool still
  requires a Django credential and refuses clearly when one is missing, telling the caller to
  sign up first.
- New tool: create an account (email, username, password, country), reusing the same signup
  validation Django already applies. On success, the caller's session gains a Django credential
  immediately, without needing to reconnect.
- New tool: request a password-reset code by email. The response is identical whether or not the
  address has an account, so a caller cannot use it to discover who has signed up.
- New tool: complete a password reset with the emailed code and a new password.
- New tool: change the caller's own password, given their current password - available once a
  caller has a Django credential (an existing account, whether from before or from a signup
  earlier in the same session).
- **BREAKING** (operationally, not in any tool's request/response contract): a caller with no
  Django account is no longer refused before reaching the MCP session; they reach it with fewer
  tools available instead. Anything relying on "no account means no session" changes behavior.

## Capabilities

### New Capabilities

- `mcp-auth-tools`: the signup, forgot/reset-password, and self-service change-password tools
  this server exposes, their inputs, and what a caller does and doesn't learn from each.

### Modified Capabilities

- `mcp-session-auth`: a caller with no Django account is admitted to a session (with no Django
  credential) instead of being refused, so they can reach the signup tool.

## Impact

- `mcp_server/server.py`: `CredentialVerifier` no longer refuses a caller solely because Django
  reports no matching account; every tool but signup gains a check for a missing Django
  credential.
- `mcp_server/django_client.py`: gains functions for signup, password-reset request, password-
  reset confirm, and the self-service change-password call; `exchange_google_token` distinguishes
  "Google itself refused the token" from "no Django account for this identity" so the verifier
  can tell the two apart.
- No changes to `sdd_django_demo/` - signup and both password-reset endpoints already exist and
  are used as-is; the self-service change-password endpoint they call was added separately, on
  `django-user-reporting-and-google-auth`.
