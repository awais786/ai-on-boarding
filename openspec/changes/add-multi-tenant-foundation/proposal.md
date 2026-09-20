## Why

The API serves one flat pool of users. GitHub issue #80 asks for one deployment to serve many
organizations whose users, credentials and data are kept apart. This is PR 1 of 3: it lays the
foundation - organizations, tenant-aware signup and signin, and server-side isolation of what
already exists. Roles and tenant administration (PR 2) and password-reset hardening (PR 3) build
on it and are out of scope here.

## What Changes

- Add **organizations**: a name, a unique slug, created/updated timestamps, and an active/inactive
  status. Every user belongs to exactly one organization.
- Organizations are created by an operator, not through the public API. Each has a **join code**
  that is shown once, at creation.
- **Signup** names an organization (by slug) and presents its join code. A caller cannot join an
  organization without its join code, and a failed join does not reveal whether the organization
  exists.
- **Email and username are unique per organization**, not globally: two organizations may each
  have a user with the same email or username.
- **Signin** names an organization. Credentials that are valid in a different organization are
  rejected exactly like a wrong password. Lockout after repeated failures is counted per
  organization.
- **Authenticated requests** carry the organization of the signed-in user. It is never taken from
  client input. A token stops working the moment its user or its organization is deactivated.
- The existing user list and admin change-password endpoints only ever see, and only ever change,
  users in the caller's own organization. An id or username from another organization behaves as
  if it does not exist.
- **Password-reset request** names an organization, so an email shared by users in two
  organizations resolves to the right one. Reset hardening beyond that is PR 3.
- Existing users are moved into a single default organization by the migration, with signup into it
  closed until an operator issues a join code.
- **BREAKING**: signup, signin and password-reset request each gain a required `organization`
  field, and signup also gains a required `join_code`. Callers that omit them are rejected. The
  MCP server calls these endpoints and needs a matching update, tracked separately.

## Capabilities

### New Capabilities

- `tenant-organizations`: what an organization is, how one is created and deactivated, how its
  join code works, and that every user belongs to exactly one.
- `tenant-isolation`: how the tenant of an authenticated request is established, and the
  guarantees that a user, an inactive user or an inactive organization can never reach another
  organization's users.

### Modified Capabilities

- `user-signup`: signup joins a named organization with its join code; duplicate email and
  username are judged within that organization.
- `user-signin`: signin names an organization; lockout is per organization; inactive users and
  organizations are refused.
- `user-password-reset`: a reset request names an organization, and the address is looked up
  within it.

## Impact

- `sdd_django_demo/api/`: models (organization, per-user membership), migrations (schema, plus a
  data migration for existing users), serializers, signin/signup/reset views, the token
  authentication used by protected endpoints, and the Google sign-in resolution.
- Two operator management commands for creating an organization and rotating its join code.
- Existing tests for signup, signin, password reset, user list and admin change-password must be
  updated for the new required fields.
- `mcp_server/` calls these endpoints and will break until updated; that work is a separate PR.
- No new third-party dependency.
