# Implementation Plan: User Signin

**Branch**: `002-user-signin` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-user-signin/spec.md`

## Summary

Add a single endpoint that authenticates an email and password against an existing account and
returns an opaque token on success. Any failure — unregistered email, wrong password, or an
email currently locked out — returns the identical 401 response, so a caller can never tell which
of the three was true. Three failures against the same email within 5 minutes lock that email out
for 30 minutes; a success resets the count. Implemented using Django REST Framework, with pytest
and pytest-django for tests, following the conventions established by the signup feature.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Django 6.1, Django REST Framework 3.18.0, drf-spectacular 0.30.0,
`rest_framework.authtoken` (bundled with DRF, already in `INSTALLED_APPS`)

**Storage**: SQLite, default settings, no environment variables required

**Testing**: pytest 9.1.1 with pytest-django 4.14.0

**Target Platform**: Linux/macOS server

**Project Type**: web-service

**Performance Goals**: none stated; signin is not on a hot path

**Constraints**: no new runtime dependency; lockout state must survive across requests without
requiring a shared cache backend the scaffold doesn't already have

**Scale/Scope**: one endpoint, one serializer, one new model (lockout tracking — see Design
decisions for why this is the one place this feature needs new state, unlike signup)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I — every behavioural requirement has automated verification | PASS by construction: each of FR-001…FR-014 is testable, and `traceability.md` (written after implementation) confirms none is left untested |
| II — security-sensitive behaviour has explicit tests | FR-008, FR-011, FR-012, FR-013 are all directly security-relevant (enumeration, credential exposure, brute force) and each requires a direct assertion, not incidental coverage |
| III — follow existing Django and DRF conventions | Reuses the signup feature's serializer/view split, its `email` normalisation pattern, and the scaffold's existing `test_*.py` naming |
| IV — prefer simple solutions over unnecessary abstractions | One new model, chosen specifically because it is simpler and more testable than reaching for a cache backend the scaffold does not configure (see Design decisions) |
| V — tests are never modified to make an implementation pass | Process constraint |
| VI — specifications may evolve | Process constraint |
| VII — a specification change propagates outward | The lockout thresholds (FR-012) are the value most likely to change, and they appear in exactly one place: a small module-level constants block, not scattered through the view |
| VIII — code is generated from instructions, never hand-written | Process constraint |
| IX — recurring technique belongs in a project skill | Not yet applicable |
| X — tests are written after the implementation, from the specification | `/speckit-tasks` is instructed below to generate no test tasks |

**Gate result**: no violations. The one new model is addressed explicitly in Complexity Tracking
below, since Principle IV creates a presumption against new state that this decision has to earn.

**Post-design re-check**: Phase 1 design (data-model.md, contracts/signin.md) introduces exactly
the one model already justified in Complexity Tracking, no new dependency, and no further
deviation from the constitution. Gate result unchanged: no violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-user-signin/
├── plan.md              # this file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── signin.md         # Phase 1 output
└── tasks.md              # Phase 2 output (/speckit-tasks — not created by /speckit-plan)
```

### Source Code (in `sdd_django_demo/`)

```text
sdd_django_demo/
└── api/
    ├── models.py            # new — SigninAttempt, tracks lockout state
    ├── migrations/
    │   └── 0001_signinattempt.py  # new
    ├── serializers.py       # modified — adds SigninSerializer alongside signup's
    ├── views.py              # modified — adds the signin endpoint alongside signup and health
    ├── urls.py                # modified — route for signin
    └── test_signin.py         # new — written after implementation, from the specification
```

**Structure Decision**: Single project, single existing Django app. Signin is a second endpoint
on the same `api` app signup already extended; no new Django app.

## Design decisions

**Authentication goes through Django's `authenticate()`, not a manual password comparison.**
`authenticate()` already returns `None` uniformly for "no such user" and "wrong password" — the
two cases FR-008 requires to be indistinguishable arrive at the view as the same `None`, so the
identical-response requirement falls out of using the standard call rather than needing to be
implemented as a special case. The account is looked up by `username`, which signup already
populates with the normalised email (see `specs/001-user-signup/plan.md`, Design decisions), so
no separate email-to-user lookup is needed before calling `authenticate()`.

**Signin issues a DRF auth token.** `rest_framework.authtoken` is already installed (added during
the scaffold's setup, ahead of this feature, specifically because signin was known to need it).
`Token.objects.get_or_create(user=user)` satisfies FR-009 without a new dependency.

**Lockout state is a new model, not the Django cache framework — the one deliberate exception to
"no new model" set by signup.** FR-012's rule ("3 failures within 5 minutes → 30-minute lockout")
needs state that survives across requests and is visible to tests via ordinary ORM assertions.
The scaffold has no cache backend configured beyond Django's process-local default, which is not
safely shared across multiple workers and complicates asserting "the count reset" in a test
without reaching into cache internals. A model queried through the ORM is simpler to test and
matches Principle IV's spirit — the simplest solution that is actually verifiable — even though
it is not the simplest possible mechanism in isolation. See Complexity Tracking.

**`SigninAttempt` tracks one row per email, not one row per attempt.** Fields: `email`,
`failed_count`, `last_failed_at`. On a failure: if `last_failed_at` is unset or more than 5
minutes old, the window has expired and `failed_count` resets to 1; otherwise it increments. Once
`failed_count` reaches 3, the account is locked until `last_failed_at + 30 minutes` (FR-012). A
success sets `failed_count` to 0 (FR-014). This is a state machine, not a log — it answers "is
this email locked right now" in one row lookup, rather than requiring a windowed aggregate query
over a growing attempts table.

**Attempts made during lockout do not extend the lockout.** The specification does not say
whether hammering a locked email should push the unlock time further out. Extending it would let
an attacker keep a real user locked out indefinitely just by continuing to try; not extending
means lockout always self-heals 30 minutes after the third failure, which this plan treats as the
safer default given it is not stated. Recorded here rather than left to be discovered in the code,
per Principle VII.

**`SigninAttempt` rows are keyed on the submitted email, including emails that are not
registered.** FR-012 says "against the same email," not "against the same account" — tracking
unregistered emails too means repeatedly probing nonexistent addresses is itself rate-limited,
consistent with FR-008 treating both failure modes identically.

## Complexity Tracking

> Fill only if Constitution Check has violations that must be justified

| Addition | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New model `SigninAttempt` (Principle IV presumes against new state) | FR-012–FR-014 require lockout state that survives across requests and is assertable in tests | Django's cache framework was considered and rejected: the scaffold's default cache backend is process-local, is not guaranteed consistent across multiple workers in a real deployment, and tests would need to reach into cache internals rather than assert against the database the rest of the suite already uses |
