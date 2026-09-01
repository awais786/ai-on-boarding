## Context

`user-signup` (archived) originally established the account model: Django's built-in `User`,
email as the sole identifier, `User.username` populated internally from the normalised email.
This change modifies that: `user-signup` gains a real, independently-chosen `username` field
using the same `User.username` column Django already provides (it's `unique=True` out of the
box, so no new migration is needed for the column itself - only the application logic that
populates and validates it changes). See `openspec/specs/user-signup/spec.md` and
`openspec/changes/archive/2026-08-19-add-user-signup/`.

## Goals / Non-Goals

**Goals:**
- Satisfy every requirement in `specs/user-signin/spec.md` and the `specs/user-signup/spec.md`
  delta, especially the identical-rejection guarantee, without it being a special case someone
  could accidentally break later.

**Non-Goals:**
- No rate limiting beyond the specific 3-attempts/5-minute/30-minute lockout rule.
- No password reset, no "remember me," no refresh tokens.
- No atomic guard against a rare concurrent cross-field race (see Risks below).

## Decisions

**Username reuses Django's built-in `User.username` column - no new migration for the field
itself.** It already carries `unique=True`. Signup now populates it from the submitted username
(normalised to lowercase) instead of from the email, and validates it directly instead of
deriving it silently.

**Username format: 3-30 characters, letters/digits/underscore only, normalised to lowercase
before storage and comparison - mirrors the existing email normalisation precedent.**

**A `post_migrate` signal handler adds a genuine unique index on `auth_user.email`, via raw
SQL - not a migration.** Previously, email's race protection was accidental: `username` was
always set equal to `email`, so Django's built-in `unique=True` on `username` doubled as email's
DB-level defense (see the archived `add-user-signup` design.md, "the second would hit an
unhandled IntegrityError on the username unique constraint"). Once `username` is independent of
`email`, that protection disappears for email - two concurrent signups with the same email but
different usernames would both pass the pre-check and both succeed, silently breaking the
already-shipped "reject a duplicate email... including when two submissions race" requirement.
No expression index is needed since email is already normalised to lowercase before storage.

A `migrations.RunSQL` (and, separately, a `migrations.RunPython` running the identical SQL
through a raw cursor) migration was tried first and rejected: under this project's test runner,
the index was reliably recorded as applied in `django_migrations` but did not exist afterward in
the database the tests then queried - reproducible in isolation, independent of `:memory:` vs a
file-based test database, and independent of RunSQL vs RunPython. Executing the identical SQL
from a `post_migrate` signal handler (`ApiConfig.ready()` in `api/apps.py`, connected to
`django.db.models.signals.post_migrate`) - i.e. as ordinary code that runs once migrations
finish, not as a migration operation itself - was verified to persist reliably in both the dev
database and the test suite. The signal handler uses `CREATE UNIQUE INDEX IF NOT EXISTS` so it
is safe to run on every `migrate` invocation. This does not require a custom user model or
`AUTH_USER_MODEL` change.

**Username and email can never collide for accounts created through `SignupSerializer`, by
construction of the username format rule - no explicit cross-check needed there.** A valid
email always contains `@` and a domain; the username format (letters, digits, underscore only)
forbids both characters. So no string submitted to signup can pass both fields' format
validation, which makes `Q(email=email_or_username) | Q(username=email_or_username)` return at
most one row for any account this API created. An earlier version of this design added explicit
cross-checks (username must not equal an existing email, and vice versa) - removed once
implementation revealed they were unreachable through this API: by the time either check would
run, the colliding value would already have failed the *other* field's format validation.

**Known accepted risk: this guarantee does not extend to accounts created outside
`SignupSerializer`.** `/code-review`'s second pass correctly noted that an account created via
`manage.py createsuperuser`, the Django admin, or a fixture/data migration is not subject to
`SignupSerializer.validate_username`/`validate_email` at all, so such an account's `username`
could be set to a string that collides with a different account's `email` (or vice versa). If
that happens, `User.objects.filter(Q(email=email_or_username) |
Q(username=email_or_username)).first()` could match either account, nondeterministically. Not
fixed here: closing this fully would mean validating uniqueness-across-both-fields at the `User`
model or admin level, which is outside what this change's specs (signup and signin, both scoped
to this API's own endpoints) govern. Accepted for this project's scope; would need revisiting
before this design is reused somewhere admin-created accounts are routine.

**Authenticate through Django's `authenticate()`, not a manual password comparison - but now
preceded by an explicit account lookup.** Because `authenticate(username=..., password=...)`
takes a `username`, and the submitted value could be either the account's email or its username,
the view first resolves the candidate account via the `Q(email=...) | Q(username=...)` lookup
above, then calls `authenticate(username=<that account's actual username>, password=...)`. If no
candidate account is found, the view treats it exactly like `authenticate()` returning `None` and
proceeds to the same rejection branch as a wrong password - preserving the identical-rejection
guarantee by symmetry of code path, not by literally reusing `authenticate()`'s single return
value. Alternative considered: look up `User.objects.get(...)` then call `check_password()`
directly - rejected for the same reason as the original decision: it requires manually keeping
the "not found" and "wrong password" response branches byte-identical.

**Missing-field rejections return 401 with a field-named body, not DRF's default 400.**
"Return HTTP 401 on rejection" states signin returns 401 "for any reason," and the
missing-email-or-username/missing-password requirements each require the response to name the
offending field. The identical-rejection requirement only binds three enumerated failure modes
(unregistered, wrong password, lockout) - it does not cover missing-field validation, so a
distinct field-named body at 401 is consistent with both requirements. The view checks
`serializer.is_valid()` without `raise_exception=True` and returns `Response(serializer.errors,
status=401)` on failure, instead of letting DRF's default exception handling return 400.

**Token via `rest_framework.authtoken`, already installed.** `Token.objects.get_or_create(user=
user)` returns the same token on repeated signin (per spec's "repeated signin succeeds again"
scenario) without minting a new one each time, and needs no new dependency.

**Lockout state is a new model (`SigninAttempt`), not the Django cache framework - the first
departure from `user-signup`'s "no new model" precedent.** The scaffold configures no cache
backend beyond Django's process-local default, which is not reliably shared across multiple
worker processes and is awkward to assert against directly in a test. A model keeps lockout state
in the same database the rest of the suite already asserts against. One row per submitted email
or username (not one row per attempt): `email_or_username`, `failed_count`, `last_failed_at`. On
a failure, if `last_failed_at` is unset or more than 5 minutes old, the window has expired and
`failed_count` resets to 1; otherwise it increments. At `failed_count >= 3`, the row is locked
until `last_failed_at + 30 minutes`. Success sets `failed_count` to 0.

**`SigninAttempt` is keyed on the resolved account's canonical email when the submitted value
resolves to an account, and on the raw (normalised) submitted value when it does not.** An
earlier version of this decision keyed purely on the submitted string, regardless of resolution -
`/code-review` caught that this lets an attacker evade lockout entirely: 3 failures via the
account's email, then 3 more via its username, then 3 more back via email once the first window
lapses, and so on indefinitely, since each string got its own `SigninAttempt` row. Resolving the
candidate account first (the same lookup already needed for authentication) and keying on its
canonical email closes this - both the email and the username of one account now share one
counter. Values that resolve to no account still get their own per-string row, so repeatedly
probing nonexistent emails or usernames remains rate-limited too, consistent with treating every
failure mode identically.

**The `SigninAttempt` read-modify-write is wrapped in `transaction.atomic()` with
`select_for_update()`.** A second `/code-review` pass (run after the lockout-keying fix above,
since the project's review contract allows an initial pass plus one follow-up) found the original
read-then-save of `failed_count` had no locking: concurrent requests against the same account
could all read the same stale count before any of them saved, undercounting real failures and
letting an attacker exceed the 3-attempt threshold without ever being locked out. Locking the row
for the duration of the check-and-update closes this on any backend that supports row-level
locking (Postgres, MySQL); SQLite (used by this project's dev/test setup) has no
`select_for_update()` support, so Django silently treats it as a plain `SELECT` there - the fix is
inert under SQLite specifically, but correct and necessary for a real deployment. No dedicated
concurrency test was added: simulating a genuine race reliably requires a backend with real
row-level locking, and a thread-based test against SQLite would be flaky rather than a meaningful
verification of the lock itself.

**Attempts made during lockout do not extend the lockout.** Not stated by the spec either way;
extending it would let an attacker keep a real user locked out indefinitely just by continuing to
try. Not extending means lockout always self-heals 30 minutes after the third failure - the safer
default given it's unstated, recorded here rather than left to be discovered in the code.

## Risks / Trade-offs

- [New model adds a migration] → justified explicitly above rather than left implicit; the
  simpler cache-based alternative was considered and rejected for testability reasons specific to
  this scaffold.
- [Lockout tracked per account (or per unresolved value), not per IP] → a distributed attacker
  spreading attempts across many source addresses is still rate-limited by this rule; a
  legitimate user retrying from multiple devices shares one counter. Accepted trade-off, not
  revisited unless it causes real friction.
- [Cross-field collision check is not atomic] → two concurrent signups - one choosing an email,
  the other independently choosing the same string as a username - could both pass validation
  before either commits, since the check queries at validation time rather than holding a
  cross-column lock. Accepted for this scaffold's scale; a real deployment would need a
  database-level constraint or serializable transaction to close this gap.
- [`openspec/config.yaml`'s `context` block still says "No username field exists anywhere"] →
  needs a follow-up edit once this change's wording is final; tracked outside this change's
  artifacts since config.yaml is a project-wide file, not scoped to one change.
- [Unique index added directly on `auth_user`, a table owned by `django.contrib.auth`, not this
  app] → deliberate; both migrations and signal handlers can run arbitrary SQL against any
  table. No `AUTH_USER_MODEL` change or custom user model needed.
- [Index created by a `post_migrate` signal handler instead of a migration] → unusual, but the
  migration-based approach was empirically unreliable in this project's test environment (see
  the Decisions section above); the signal handler was verified to work. Trade-off: the index's
  existence isn't tracked in `django_migrations` the way a schema change normally would be -
  acceptable here since `CREATE UNIQUE INDEX IF NOT EXISTS` is idempotent and cheap to re-run on
  every migrate.
