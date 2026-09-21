## 1. Models and migrations

- [x] 1.1 In `sdd_django_demo/api/models.py`, add `Organization` (name, unique lowercase slug with a
  `[a-z0-9-]` validator, `created_at`, `updated_at`, `is_active`, `join_code_digest` blank by
  default) and a helper to issue a join code that returns it once and stores only its SHA-256
- [x] 1.2 Add `TenantQuerySet.for_organization(org)` and `users_in(org)` in a new
  `sdd_django_demo/api/tenancy.py`; this is the only place organization filtering is written
- [x] 1.3 Add `Membership` (one-to-one to `User`, foreign key to `Organization`, lowercase `email`
  and `username`) with named unique constraints on `(organization, email)` and
  `(organization, username)`, each name containing `email` or `username`
- [x] 1.4 Widen `SigninAttempt.email_or_username` to hold `"<slug>|<identifier>"`
- [x] 1.5 Generate the schema migration; first check `showmigrations api` and resolve the existing
  numbering (two `0001_*` files, no `0003`) so the new migration has a single parent
- [x] 1.6 Add the data migration: create the `default` organization with a blank join digest and one
  `Membership` per existing user with lowercased email and username; abort with a message naming
  the accounts if two would collide; write the reverse migration
- [x] 1.7 Remove the `post_migrate` hook in `sdd_django_demo/api/apps.py` and add a migration that
  drops the global unique index on `auth_user.email` (reverse recreates it), so the same email can
  exist in two organizations
- [x] 1.8 Add `django.contrib.sites` to `INSTALLED_APPS`; add `Organization.site` (required
  one-to-one to `Site`, `PROTECT`) with a migration that adds it nullable, gives the `default`
  organization a `Site` whose domain is the host of `RESET_LINK_BASE_URL` (reusing a row with that
  domain), then makes it required; include a reverse

## 2. Tenant resolution and authentication

- [x] 2.1 Add `TenantTokenAuthentication` in `sdd_django_demo/api/authentication.py`: one
  `select_related` query for token, user, membership, organization; reject an inactive user, a
  missing membership, or an inactive organization on every request, caching nothing
- [x] 2.2 Add one helper that returns the caller's organization from `request.user.membership`, and
  one helper that resolves an active organization from a body slug
- [x] 2.3 Set `DEFAULT_AUTHENTICATION_CLASSES` in settings to `TenantTokenAuthentication` only, and
  remove the per-view `TokenAuthentication` in `mcp_views.py`

## 3. Signup

- [x] 3.1 Add `organization` and `join_code` to `SignupSerializer`; in `validate()` resolve the
  organization and compare the code with `hmac.compare_digest`; raise one error keyed on
  `join_code` for unknown, inactive, no-code and wrong-code alike
- [x] 3.2 Only after that check, run the duplicate email and username checks against
  `Membership` within the organization
- [x] 3.3 In `create()`, inside one `transaction.atomic()`, create the `User` with a random 32-char
  hex username and the mirrored email, the `Membership`, and the country record; map the
  per-organization `IntegrityError` to the same field-keyed error as an ordinary duplicate
- [x] 3.4 Make `AccountSerializer` read `username` and `email` from `Membership`

## 4. Signin

- [x] 4.1 Add `organization` to `SigninSerializer`
- [x] 4.2 In `SigninView`, find the `Membership` in the resolved active organization by email or
  username, verify with `check_password`, then require the user and organization to be active and
  keep the embargo check
- [x] 4.3 Key `SigninAttempt` on `"<slug>|<identifier>"` (the account's email once found) and
  return `SIGNIN_REJECTION_BODY` with 401 for every failure, including an unknown organization

## 5. Reset request and Google sign-in

- [x] 5.1 Add `organization` to `PasswordResetRequestSerializer`; look the address up only among
  the named active organization's active accounts and use `Membership.email` as the recipient
- [x] 5.2 Key `PasswordResetAddressThrottle` on `"<slug>|<email>"`; an unknown or inactive
  organization takes the same uniform 200 path as an unregistered address
- [x] 5.3 Change `resolve_google_user` to query `Membership.email`, return nothing for an
  ambiguous match, an inactive user, or an inactive organization
- [x] 5.4 Build the reset link from the account's organization: keep the scheme and path prefix of
  `RESET_LINK_BASE_URL`, replace the host with `organization.site.domain`, and never read the host
  from the request

## 6. Scoped endpoints

- [x] 6.1 Make `UserListView` build its queryset from `users_in(organization)` and read `username`
  from `Membership`, including the username filter
- [x] 6.2 Make `AdminChangePasswordView` look the target up in `users_in(organization)` by
  `Membership.username`, so another organization's username returns the ordinary 404
- [x] 6.3 Make `UserAccountSerializer` read `username` from `Membership`

## 7. Operator tooling

- [x] 7.1 Add `create_organization <name> <slug>` and `rotate_join_code <slug>` management commands
  under `sdd_django_demo/api/management/commands/`; each prints the join code once
- [x] 7.2 Register `Organization` in `sdd_django_demo/api/admin.py` without exposing the digest, so an
  operator can toggle `is_active`
- [x] 7.3 Change `create_organization` to `<name> <slug> <domain>`: validate the domain is a bare
  host (no scheme, no path), create the `Site` and the `Organization` in one transaction, and show
  the domain in `OrganizationAdmin`

## 8. Tests (after implementation, from the spec)

- [x] 8.1 List every requirement and scenario in `specs/tenant-organizations`,
  `specs/tenant-isolation`, and the modified `user-signup`, `user-signin` and
  `user-password-reset` deltas, and what a test would need to assert, working only from the spec
- [x] 8.2 Update the existing `test_signup.py`, `test_signin.py`, `test_password_reset.py`,
  `test_user_management.py`, `test_google_auth.py` and `test_self_change_password.py` for the new
  required fields and the two-organization fixtures in `conftest.py`
- [x] 8.3 Write tenant-isolation tests from that list: Tenant A user list and admin password change
  never reach Tenant B, a Tenant B username answers like a nonexistent one, an organization named
  in the body or a header is ignored on an authenticated request
- [x] 8.4 Write authentication tests: signin within the tenant, refused against another tenant,
  inactive user and inactive organization refused, an existing token refused after deactivation
  and accepted after reactivation, a token with no membership refused
- [x] 8.5 Write signup tests: join code accepted and refused, the four organization failures
  indistinguishable, the same email and username allowed across two organizations and refused
  within one, a concurrent duplicate within one organization, and the join code absent from
  every response
- [x] 8.6 Write per-organization lockout and reset-request tests: failures in one organization do
  not lock out the same email in another, reset resolves to the named organization only, and a
  flood in one organization does not throttle the other
- [x] 8.7 Write migration and command tests: existing users land in the default organization and can
  sign in, the default organization is closed until rotated, rotating invalidates the old code,
  and the stored digest is not the code
- [x] 8.8 Run `pytest` in `sdd_django_demo/` and confirm the whole suite passes
- [x] 8.9 Prove at least one new test can fail: temporarily remove the organization filter from
  `users_in`, confirm the cross-organization list test goes red, then restore it
- [x] 8.10 Write tests from the revised specs: an organization has a unique domain, a domain with a
  scheme or path or a missing domain is refused, the reset link carries the organization's own
  domain, two organizations get two hosts, and a forged `Host` header does not change the link;
  update the existing reset-link tests, the factories and the migration tests for the `Site` link
- [x] 8.11 Re-run `pytest` for the whole project and confirm it passes; upgrade a scratch database
  that holds the pre-`Site` migrations and confirm the default organization gets its `Site`

## 9. Traceability and review

- [x] 9.1 Build `traceability.md` mapping every requirement in the five delta specs to its code and
  its test
- [x] 9.2 Post the proposal and the full delta specs to GitHub issue #80 via `gh issue comment`
- [ ] 9.3 Run `/code-review` and record the verdict
- [ ] 9.4 Fix every blocking finding, then run `/code-review` once more (verify-only) for a final
  `Ready to merge:` verdict
