## Context

`user-signup` (archived) already established the account model: Django's built-in `User`, email
as the only identifier, `User.username` populated internally from the normalised email. See
`openspec/specs/user-signup/spec.md` and `openspec/changes/archive/2026-08-19-add-user-signup/`.

## Goals / Non-Goals

**Goals:**
- Satisfy every requirement in `specs/user-signin/spec.md`, especially the identical-rejection
  guarantee, without it being a special case someone could accidentally break later.

**Non-Goals:**
- No rate limiting beyond the specific 3-attempts/5-minute/30-minute lockout rule.
- No password reset, no "remember me," no refresh tokens.

## Decisions

**Authenticate through Django's `authenticate()`, not a manual password comparison.**
`authenticate()` already returns `None` uniformly for "no such user" and "wrong password" - the
two cases the identical-rejection requirement needs indistinguishable arrive at the view as the
same `None`, so that guarantee is a consequence of using the standard call rather than a branch
someone has to remember to keep in sync. Alternative considered: look up `User.objects.get(email=
...)` then call `check_password()` - rejected because it requires manually keeping the
"not found" and "wrong password" response branches byte-identical, which is exactly the
duplication the requirement is trying to prevent.

**Token via `rest_framework.authtoken`, already installed.** `Token.objects.get_or_create(user=
user)` returns the same token on repeated signin (per spec's "repeated signin succeeds again"
scenario) without minting a new one each time, and needs no new dependency.

**Lockout state is a new model (`SigninAttempt`), not the Django cache framework - the first
departure from `user-signup`'s "no new model" precedent.** The scaffold configures no cache
backend beyond Django's process-local default, which is not reliably shared across multiple
worker processes and is awkward to assert against directly in a test. A model keeps lockout state
in the same database the rest of the suite already asserts against. One row per email (not one
row per attempt): `email`, `failed_count`, `last_failed_at`. On a failure, if `last_failed_at` is
unset or more than 5 minutes old, the window has expired and `failed_count` resets to 1;
otherwise it increments. At `failed_count >= 3`, the email is locked until
`last_failed_at + 30 minutes`. Success sets `failed_count` to 0.

**`SigninAttempt` is keyed on the submitted email regardless of whether an account exists for
it.** The requirement says "against the same email," not "against the same account" - tracking
unregistered emails too means repeatedly probing nonexistent addresses is itself rate-limited,
consistent with treating every failure mode identically.

**Attempts made during lockout do not extend the lockout.** Not stated by the spec either way;
extending it would let an attacker keep a real user locked out indefinitely just by continuing to
try. Not extending means lockout always self-heals 30 minutes after the third failure - the safer
default given it's unstated, recorded here rather than left to be discovered in the code.

## Risks / Trade-offs

- [New model adds a migration] → justified explicitly above rather than left implicit; the
  simpler cache-based alternative was considered and rejected for testability reasons specific to
  this scaffold.
- [Lockout tracked per email, not per IP] → a distributed attacker spreading attempts across many
  source addresses is still rate-limited by this rule; a legitimate user retrying from multiple
  devices shares one counter. Accepted trade-off, not revisited unless it causes real friction.
