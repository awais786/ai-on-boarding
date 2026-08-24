## Context

`user-signup` and `user-signin` (both archived) already establish the account model - Django's
built-in `User`, email as the only identifier, no custom user model - and the pattern each
serializer follows: field-level `validate_<field>` methods/functions raising `ValidationError`
to name the offending field. See `openspec/specs/user-signup/spec.md`,
`openspec/specs/user-signin/spec.md`, and their archived changes for the reference shape.

## Goals / Non-Goals

**Goals:**
- Satisfy every requirement in `specs/embargo/spec.md` and the `user-signup`/`user-signin` deltas
  in this change, with no gap between what the blocked-country list says now and what signup and
  signin enforce.

**Non-Goals:**
- No admin UI beyond Django's built-in admin for managing the blocked-country list.
- No IP-based or other geolocation - the country is exactly what the caller submits at signup.
- No proactive action against an already-issued token when its account's country becomes
  blocked - other authenticated endpoints keep working until that account's next signin attempt.
- No canonicalisation of country spelling (e.g. no ISO-code mapping) - matching is a
  case-insensitive string compare, per `specs/embargo/spec.md`'s own requirement, nothing more.

## Decisions

**A new Django app, `embargo`, separate from `api`.** Unlike `user-signin`'s `SigninAttempt`
(a piece of auth-internal state with no meaning outside signin), the blocked-country list and the
check against it are not inherently about authentication - they are a general policy concern that
already now gates two unrelated endpoints (signup and signin) and could plausibly gate more later.
The proposal already treats `embargo` as its own capability with its own spec file; a matching
Django app keeps that boundary real in code, and keeps `api` scoped to the auth endpoints
themselves rather than absorbing an unrelated rules table. Alternative considered: add the
blocklist as one more model in `api`, following `SigninAttempt`'s precedent - rejected because
`SigninAttempt` is genuinely signin-internal bookkeeping, while embargo is a distinct concern
`api` only *consumes*, not owns.

**Two models in `embargo`, both minimal:**
- The blocked-country list: one row per blocked country (`country`, unique). Absence of a row
  means allowed, per `specs/embargo/spec.md`'s fail-open requirement - the table only ever needs
  to name exceptions.
- The account's country: one row per account, recording the country submitted at that account's
  signup (`user`, one-to-one to `auth.User`; `country`). This is what `specs/user-signin/spec.md`'s
  new requirement checks - the country *as submitted at signup*, not something re-submitted at
  signin (signin's own request shape is unchanged: email and password only).

**`embargo` exposes a check, not just data.** `api` calls into `embargo` for two things: "is this
country currently blocked" (used by both signup's field validation and signin's post-auth check)
and "record this account's country" (used once, at signup). `api` never queries `embargo`'s models
directly, matching the same boundary the new app exists to keep.

**Country comparison is case-insensitive by normalising both sides to lowercase at check time** -
consistent with how email is already normalised elsewhere in this codebase, and satisfying
`specs/embargo/spec.md`'s case-insensitivity requirement without needing a database-level
case-insensitive collation SQLite doesn't provide.

**Signup: reject via a field-level validator, before account creation.** `country` becomes a
third field on `SignupSerializer`, validated the same way `email` and `password` already are - a
`validate_country` step calls `embargo`'s check and raises `ValidationError` naming the `country`
field if blocked, before `create()` ever runs. No account is created for a blocked-country
submission, and the account's country is recorded only on the success path, after the `User` is
created.

**Signin: the embargo check runs only after a successful password authentication, and does not
touch the lockout counter.** `authenticate()` already returns `None` uniformly for "no such user"
and "wrong password" (see the archived `add-user-signin` design.md); embargo can only apply to an
account that authentication has already confirmed exists and matched the password, so the check
runs right after `authenticate()` succeeds and before a token is issued - if blocked, the view
returns the same fixed 401 body used for every other rejection, without creating or issuing a
token. It deliberately does not increment `SigninAttempt.failed_count`: the credentials were
correct, so counting this as a "failed guess" would conflate two unrelated concepts and could
eventually lock out a legitimate accountholder for repeatedly proving they know their own
password. An account with no recorded country (a pre-existing account, or any other edge case)
is treated as allowed - consistent with the same fail-open default the blocklist itself uses.

## Risks / Trade-offs

- [New Django app and two new models] → justified above; kept intentionally minimal - no fields,
  admin customisation, or endpoints beyond what the stated requirements need.
- [Free-text, case-insensitive country matching, no canonical spelling list] → a submission using
  an unexpected spelling or alternate name for a blocked country (e.g. a country's name in
  another language) will not match. Accepted: no requirement asks for canonicalisation, and
  adding one now would be solving a problem nobody has written down.
- [No proactive effect on outstanding tokens] → explicit non-goal above, not an oversight; an
  embargoed account's existing token still works for non-signin requests until its next signin.
