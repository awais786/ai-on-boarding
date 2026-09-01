## Why

Signup and signin currently accept anyone regardless of location. The product needs a way to
restrict both by country, starting with a concrete rule: submissions from India are not allowed
to sign up, and accounts already registered from a country that becomes restricted must not go
on signing in as if nothing changed.

## What Changes

- Add a `country` field to signup. A submission from a currently-blocked country is rejected.
- Introduce a configurable list of blocked countries. Absence from the list means allowed - the
  list only ever needs to name exceptions, starting with India. The list can change over time.
- Every signin re-checks the account's stored country against the current blocked list, not just
  the country recorded at signup time - so a country blocked after an account was created affects
  that account's next signin, not only new signups.
- An embargo rejection at signin is folded into signin's existing indistinguishable-401
  guarantee: unregistered email, wrong password, lockout, and embargo all return the exact same
  response. A caller cannot learn from the response alone that an account is embargoed.

## Capabilities

### New Capabilities

- `embargo`: the blocked-countries list (denylist, fail-open, admin-configurable) and the check
  against it, shared by signup and signin.

### Modified Capabilities

- `user-signup`: add the `country` field to the signup submission and a requirement to reject a
  submission from a blocked country.
- `user-signin`: add a requirement to reject signin for an account whose stored country is
  currently blocked, and widen the existing identical-rejection requirement to cover this as a
  fourth indistinguishable failure reason alongside unregistered email, wrong password, and
  lockout.

## Impact

- `POST /api/signup/` gains a required `country` field and a new rejection reason.
- `POST /api/signin/` gains a new rejection reason, indistinguishable from its existing ones.
- A country submitted at signup must be persisted per account so it can be re-checked at signin
  time, arbitrarily long after signup - design.md covers where.
- No new runtime dependency.
