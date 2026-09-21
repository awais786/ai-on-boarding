## Context

The project reuses Django's built-in `User` (no custom user model). Sign-in issues one DRF token per
user; protected endpoints declare `TokenAuthentication` themselves, and `REST_FRAMEWORK` sets no
default authentication, so DRF's session and basic authentication are silently active everywhere
else. `User.username` is globally unique, and so is `User.email`: `api/apps.py` creates a raw-SQL
unique index on `auth_user.email` after every migrate, which the ORM does not know about. Signin, reset request
and Google sign-in all find accounts by querying `User` directly, and the user list and admin
change-password endpoints query `User` with no notion of a caller's scope. See proposal.md - Why
for motivation.

Decisions already taken with the requester (issue #80 leaves them to the team):
- The tenant is named by an `organization` **slug in the request body** on the unauthenticated
  endpoints.
- Signup is gated by a **per-organization join code**.
- Email and username are **unique per organization**, not globally.

## Goals / Non-Goals

**Goals:** one place decides "which organization is this request in"; one place builds
organization-scoped queries; per-organization uniqueness is a database constraint; every existing
endpoint that finds or lists users is made tenant-safe.

**Non-Goals:** roles/RBAC, tenant admin endpoints, invites (PR 2); reset-token hardening, rate
limits beyond what exists, session invalidation, API docs/README finalisation (PR 3); updating
`mcp_server/` (separate PR); a tenant-creation API or UI.

## Decisions

### D1. Two new models: `Organization` and `Membership`
*Traces to:* Describe an organization; Every user belongs to exactly one organization.

`Organization` holds name, slug (unique, lowercase, `[a-z0-9-]`), `created_at`, `updated_at`,
`is_active`, and `join_code_digest` (blank means signup is closed). `Membership` is a one-to-one
from `User` to `Organization` and additionally holds the account's `email` and `username`, both
lowercase, under `UniqueConstraint(organization, email)` and `UniqueConstraint(organization,
username)`.

*Why a second table:* `auth_user.username` is globally unique, so per-organization uniqueness cannot
be expressed on `User`. Putting `organization` on `Membership` also makes "exactly one
organization" a one-to-one, enforced by the database.

*Alternative rejected - swap in a custom user model with `organization`, `email`, `username`
columns:* the cleaner shape, but `AUTH_USER_MODEL` cannot be swapped safely once tables and
foreign keys (`Token`, `PasswordResetCode`, the embargo table, admin log) exist. It would also
reverse the repo's "no custom user model" convention, and would dominate a PR that is meant to be
reviewable.

*Consequence:* the credential row (`User`) and the identity row (`Membership`) are joined, and
`Membership` is the only place email/username are looked up.

### D2. `User.username` becomes an opaque internal value
*Traces to:* Keep email and username unique within an organization only.

Because two organizations may share a handle, new accounts get a random 32-character hex
`User.username` that is never shown or queried. The person's handle lives on `Membership.username`.
Hex-32 cannot collide with an existing handle, since handles are at most 30 characters. Existing
users keep their current `User.username`, which stays unique and simply stops being read.
`User.email` is written once at creation, from the same value as `Membership.email`; no code path
edits an email today, so the copy cannot drift. Serializers that return a username
(`AccountSerializer`, `UserAccountSerializer`) read it from `Membership`.

Signin finds the `Membership` in the named organization, then hands its user's opaque
`User.username` to Django's `authenticate()`. Because that value is still globally unique, the
stock `ModelBackend` checks the password and refuses an inactive account; no custom backend is
needed.

### D2a. Drop the global unique index on `auth_user.email`
*Traces to:* Keep email and username unique within an organization only.

Found while applying: the index above makes it impossible for two organizations to hold the same
email, whatever `Membership` allows. It is removed - the `post_migrate` hook in `api/apps.py` goes,
and a migration runs `DROP INDEX IF EXISTS` so databases that already have it lose it. Uniqueness
of an email is then the `(organization, email)` constraint on `Membership` and nothing else.
Reverse: the migration recreates the index, which fails if two organizations by then share an
address; that is the correct outcome for a rollback.

### D3. One tenant-resolution rule, in two phases
*Traces to:* Take the tenant from the credential, never from client input; Refuse a token whose
organization is inactive.

- **Unauthenticated endpoints** (signup, signin, reset request): the organization comes from the
  `organization` body field, looked up by slug in a single helper. An unknown or inactive slug is
  indistinguishable from any other failure on that endpoint (see D6).
- **Authenticated requests:** a `TenantTokenAuthentication` class (subclass of DRF's
  `TokenAuthentication`) loads the token, its user, membership and organization in one
  `select_related` query. It rejects the request when the user is inactive (DRF already does), when
  there is no membership, or when the organization is inactive. It runs on every request and caches
  nothing, so deactivating a user or an organization takes effect on the next call. The
  organization is then available as `request.user.membership.organization`, read through one small
  helper so views never touch client input for it.

It is set as `DEFAULT_AUTHENTICATION_CLASSES` and replaces the per-view `TokenAuthentication`.
`DEFAULT_PERMISSION_CLASSES` is `IsAuthenticated`, so an endpoint that forgets to declare its
permissions is closed, not public; signup, signin, both reset endpoints, Google sign-in and health
opt in with `AllowAny` and `authentication_classes = []`, so a stale token header cannot affect
them. The public API docs get the same treatment through `SERVE_AUTHENTICATION`.
That deliberately also removes DRF's default session and basic authentication from the API, so a
Django-admin session held by an operator cannot be used to reach tenant endpoints. Sessions are not
otherwise used by this API, so "deactivated tenant → existing session" reduces to the token case.

*Alternatives rejected:* subdomain or `X-Organization` header (declined by requester);
middleware setting a thread-local "current tenant" that a default manager reads implicitly. The
implicit form hides the filter and fails open when unset, the opposite of what an isolation
requirement wants.

### D4. Tenant filtering has one entry point
*Traces to:* Scope the user list...; Scope admin password changes...; Never reveal another organization.

A `TenantQuerySet` with a single method, `for_organization(org)`, is the only way views obtain a
tenant-scoped set. `Membership.objects.for_organization(org)` is used for every lookup by
email/username, and `users_in(org)` (one function, in the same module) returns
`User.objects.filter(membership__organization=org)` for the user list. It is written against any
model with an `organization` foreign key, so a later tenant-owned resource reuses it rather than
adding a second convention. No view filters on `organization` by hand.

Cross-organization objects are answered with the ordinary "not found" of the endpoint, so a
username in another organization and a username nowhere produce the same 404. There are no numeric
id endpoints today; if PR 2 adds one, it must go through the same entry point.

### D5. Signup: join code, and one error for every organization failure
*Traces to:* Admit a signup only with the organization's join code; Refuse an unknown, inactive or
wrongly-coded organization identically; Never return the join code.

The serializer's `validate()` resolves the organization and checks the code with Django's
`check_password` against a digest made by `make_password` (the project's password hashers). Any failure - unknown slug, inactive
organization, blank digest, wrong code - raises the same error keyed on `join_code`, and the
duplicate email/username checks run only after it, so a duplicate can never confirm that an
organization exists. Codes are 24 random bytes (`secrets.token_urlsafe`). Using the password hashers costs one slow
hash per signup, which signup already pays for the password itself.

The account is created in a single `transaction.atomic()` (user, membership, the existing
country record). A concurrent duplicate hits the per-organization unique constraint and is
mapped to the same field-keyed error as an ordinary duplicate, using the same
`IntegrityError` handling the serializer already has. The constraints are named so their
messages contain `email` or `username`, which is what that handling matches on.

### D6. Signin: per-organization lockout, one rejection
*Traces to:* Reject all failure modes identically; Lock an email out after repeated failures;
Issue a token bound to the account's organization.

Every failure - unknown or inactive organization, unknown identifier, wrong password, inactive
account, inactive organization, lockout, embargo - returns the existing `SIGNIN_REJECTION_BODY`
with 401. Where no real password check runs (unknown organization or identifier, and a locked-out
account) the view pays for one stand-in hash, as Django's own `ModelBackend` does for an unknown
username. Found in review: without it those paths answered in ~1 ms against ~200 ms for a real
member, so timing alone revealed which organizations and members exist. The lockout key becomes `"<slug>|<identifier>"`, using the account's email once an
account is found, so an attacker in one organization cannot lock out a same-email account in
another. `SigninAttempt.email_or_username` is widened to hold the longer key. Old rows keyed
the old way are never matched again and age out; they are not migrated.

### D7. Reset request and Google sign-in are made tenant-safe, not redesigned
*Traces to:* Look the address up only within the named organization; Refuse a Google sign-in for
an inactive organization.

Per-organization email uniqueness would make the reset request's `email__iexact ... first()`
pick an arbitrary organization's account, so the request now takes `organization` and looks the
address up in that organization's active accounts only. Its throttle key becomes
`"<slug>|<email>"`. Everything after the account is found (codes, expiry, one-use, completion) is
untouched; that is PR 3.

`resolve_google_user` queries `Membership.email`, still returns nothing for an ambiguous address,
and now also returns nothing for an inactive account or organization. Google sign-in carries no
organization; the organization is that of the one matching account.

### D8. Operator tooling: two management commands, plus the admin
*Traces to:* Create organizations only through an operator command; Issue a join code once; Let an
operator deactivate an organization.

`create_organization <name> <slug> <domain>` and `rotate_join_code <slug>` generate a code, store
its digest and print the code once; the first also creates the organization's `Site` (D10) in the
same transaction, and refuses a domain that carries a scheme or a path. Deactivating and reactivating an organization is done by
toggling `is_active` in the Django admin, where `Organization` is registered without exposing the
digest. No API endpoint touches organizations, so the "no public endpoint" requirement holds by
absence.

### D9. Schema and data migration
*Traces to:* Move existing users into a default organization.

One schema migration adds `Organization` and `Membership`; a data migration creates the
`default` organization (blank join digest; its `Site` is added by D10's migration) and one `Membership` per existing user with lowercased
email and username. If two existing users would collide within the default organization (not expected while the old
unique index held, but checked because it was only created by a hook) the
migration stops with a message naming them, rather than choosing between them. The reverse
migration deletes the memberships and the default organization. Both new unique constraints double as the
composite indexes for tenant-scoped lookups; the slug unique index and the foreign-key index cover
the rest.

### D10. Each organization has a `Site`, used for its domain
*Traces to:* Give every organization a unique domain; Deliver the reset link as an absolute address.

Added after review: `django.contrib.sites` is Django's own model for "a website this deployment
serves", so an organization's domain lives there rather than in a second bespoke column.
`Organization.site` is a required one-to-one to `Site` (`PROTECT`, so a `Site` in use cannot be
deleted from under an organization). `Site.domain` is already unique in the database, which is the
uniqueness requirement; `Site.name` is set to the organization's name at creation and is not kept in
sync afterwards, since nothing renames an organization.

The reset link is built from the account's organization: the scheme and any path prefix still come
from `RESET_LINK_BASE_URL`, and the host is replaced by `organization.site.domain`. The host is read
from the database, never from the request, so the protection against a forged `Host` header is
unchanged. `SITE_ID` is not set and `get_current_site` is never called: nothing here asks "which
site is this request for".

*Why a bare `Site` is not the tenant model:* the issue requires a slug, created/updated timestamps
and an active/inactive status, and `Site` has none of them. Those would have to live in a second
model anyway, so the tenant is `Organization` and `Site` is what it points at.

*Why the tenant is not resolved from the request host:* that is what `Site` is classically used for
(`acme.example.com` selects Acme). It was rejected in favour of the `organization` body slug
because it needs wildcard DNS and host configuration, makes local development and tests harder, and
would change every unauthenticated endpoint. Nothing here prevents adding it later.

*Migration:* Django's sites app seeds an `example.com` row, which is left alone. A migration adds the
column as nullable, gives the existing `default` organization a `Site` whose domain is the host of
`RESET_LINK_BASE_URL` (reusing a row with that domain if one exists), then makes the column
required. Any other organization still without one (only possible when re-applying after a
rollback, which drops the link) gets a placeholder `<slug>.invalid` `Site` for an operator to fix in
the admin, so the migration completes instead of failing on a NOT NULL. It depends on the sites
app's migrations. Reverse removes the column and the `Site` it
created.

## Risks / Trade-offs

- **Breaking API change** (required `organization` / `join_code`) → flagged **BREAKING** in the
  proposal; the MCP server breaks until its own PR lands. Existing tests are updated in this
  change.
- **Migration aborts on clashing existing accounts** (defensive: the old index normally prevented them) → the abort
  message lists them so an operator resolves them before retrying.
- **Existing staff become admins of the default organization only** → intended; role-based
  administration arrives in PR 2, and until then `is_staff` remains the admin marker inside each
  organization.
- **Google sign-in cannot serve an email that exists in two organizations** → accepted; refusing
  is safer than guessing, and it matches the existing ambiguous-match behaviour.
- **Two rows describe one identity (`User`, `Membership`)** → bounded by writing both in one
  transaction at creation and having no edit path; a future email-change feature must update both.
- **Timing side-channel on unknown vs known account in signin** (no password hash is computed
  for an unknown account) → already true before this change and not widened by it; not addressed here.
- **Two identities per organization (slug and domain)** → they only ever meet in the reset link, and
  nothing derives one from the other, so they cannot contradict each other; the domain is the
  operator's responsibility to point at a host that really serves the reset page.
- **Unfinished sibling changes** (`add-self-service-password-change`,
  `harden-google-auth-endpoints`) touch the same files → apply against current `main`, and
  rebase if they land first.

## Migration Plan

1. Deploy the migrations (organizations and memberships, default organization, then the `Site`
   link). The default organization's domain comes from `RESET_LINK_BASE_URL`.
2. Operator runs `rotate_join_code default` if signup into the default organization is wanted.
3. Operator creates further organizations with `create_organization <name> <slug> <domain>`.
4. Roll back by reversing both migrations; accounts and tokens are untouched.
