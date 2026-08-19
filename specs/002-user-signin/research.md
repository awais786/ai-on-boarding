# Phase 0 Research: User Signin

## Decision: authenticate via Django's `authenticate()` against `username=<normalised email>`

**Rationale**: Signup already stores the normalised email as both `email` and `username` on
Django's built-in `User`. `authenticate()` returns `None` for both an unknown username and a
wrong password, which is exactly the indistinguishability FR-008 requires — using the standard
call makes the identical-rejection behaviour a consequence of the design rather than a branch
someone has to remember to write identically in two places.

**Alternatives considered**: Manually look up `User.objects.get(email=...)` then call
`check_password()` — rejected because it requires the view to construct the "not found" and
"wrong password" branches separately and manually ensure their responses are byte-identical,
which is exactly the kind of duplication FR-008 is trying to prevent.

## Decision: DRF's bundled `rest_framework.authtoken` for the success response

**Rationale**: Zero new dependencies — it ships with DRF and is already in `INSTALLED_APPS`.
`Token.objects.get_or_create(user=user)` gives a stable, reusable token per user, matching the
specification's requirement that signing in again with the same credentials succeeds again
(User Story 1, Acceptance Scenario 2) without minting a new token each time.

**Alternatives considered**: JWT — rejected as an unjustified new dependency; the constitution
(Principle IV) and the signup plan's precedent both argue against it when the built-in mechanism
already satisfies the requirement. Session-based auth (cookies) — rejected because FR-009
explicitly specifies a token in the response body, which a cookie-only approach would not satisfy
without also returning a token, at which point it is two mechanisms instead of one.

## Decision: a dedicated `SigninAttempt` model for lockout state, not the Django cache framework

**Rationale**: FR-012 needs a per-email failure counter and a timestamp that survive across
requests. The scaffold configures no cache backend beyond Django's implicit process-local default,
which does not reliably share state across multiple worker processes and is awkward to assert
against directly in a test (there is no ORM-level "assert this counter is 2" the way there is for
a model field). A model keeps the state in the same database the rest of the test suite already
asserts against.

**Alternatives considered**: `django.core.cache` with a TTL per email — rejected for the
process-sharing and testability reasons above, though it would work for a single-process
deployment; noted as a reasonable alternative if this project later adds Redis for other reasons.
A log table of every attempt (rather than one row per email) — rejected as unnecessary: FR-012
only needs "how many recent failures, how recently," which a single row's counter and timestamp
answer directly, without needing to aggregate a growing table on every request.

## Decision: lockout state is windowed by resetting on gap, not evaluated via a rolling query

**Rationale**: "3 failures within 5 minutes" could be implemented either as a query over a log
table (`COUNT(*) WHERE email=... AND created_at > now - 5min`) or as a simple state machine that
resets the counter whenever a failure arrives more than 5 minutes after the last one. The state
machine was chosen because it requires one row and one read per request rather than an aggregate
query, and because the specification's actual requirement — "is this email over the threshold
right now" — is answered by the state machine's `failed_count` field directly.

**Alternatives considered**: A rolling-window query against a per-attempt log — rejected as more
mechanism than the requirement needs, per the constitution's Principle IV.
