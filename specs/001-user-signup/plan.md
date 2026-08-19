# Implementation Plan: User Signup

**Branch**: `001-user-signup` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-user-signup/spec.md`

## Summary

Add a single write endpoint that accepts an email address and a password, validates both, and
creates exactly one account. Validation failures return a client error naming the offending
field; success returns HTTP 200 with the account's email. The stored password is not recoverable
and never appears in a response. Implemented using Django REST Framework, with pytest and
pytest-django for tests, following the conventions already in this project.

## Technical Context

**Language/Version**: Python 3.14

**Primary Dependencies**: Django 6.1, Django REST Framework 3.18.0, drf-spectacular 0.30.0

**Storage**: SQLite, default settings, no environment variables required

**Testing**: pytest 9.1.1 with pytest-django 4.14.0

**Target Platform**: Linux/macOS server

**Project Type**: web-service

**Performance Goals**: none stated; signup is not on a hot path

**Constraints**: no new runtime dependency beyond those already installed by the scaffold

**Scale/Scope**: one endpoint, one serializer, no new model

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I — every behavioural requirement has automated verification | PASS by construction: each of FR-001…FR-012 is a testable statement, and `traceability.md` (written after implementation) is the check that none is left untested |
| II — security-sensitive behaviour has explicit tests | FR-008 and FR-009 concern credential storage and exposure; both require direct assertions, not incidental coverage through a success path |
| III — follow existing Django and DRF conventions | Validation in a serializer, a thin view, tests named after behaviour — matches the scaffold's existing `api/test_health.py` style |
| IV — prefer simple solutions over unnecessary abstractions | No new Django app, no new model, no custom user model (see Design decisions) |
| V — tests are never modified to make an implementation pass | Process constraint; nothing in this design encourages it |
| VI — specifications may evolve | Process constraint |
| VII — a specification change propagates outward | The password rule (FR-006) and the response shape (FR-011) are the two decisions most likely to be revisited, and each appears in exactly one place in the design: a field validator and the output serializer, respectively |
| VIII — code is generated from instructions, never hand-written | Process constraint |
| IX — recurring technique belongs in a project skill | Not yet applicable — no project skill exists for this codebase yet |
| X — tests are written after the implementation, from the specification | `/speckit-tasks` is instructed below to generate no test tasks |

**Gate result**: no violations.

**Post-design re-check**: Phase 1 design (data-model.md, contracts/signup.md) introduces no new
model, no new dependency, and no deviation from the constitution. Gate result unchanged: no
violations.

## Project Structure

### Documentation (this feature)

```text
specs/001-user-signup/
├── plan.md              # this file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── signup.md         # Phase 1 output
└── tasks.md              # Phase 2 output (/speckit-tasks — not created by /speckit-plan)
```

### Source Code (in `sdd_django_demo/`)

This repository is a training course repo, not the application itself. The Django project lives
in `sdd_django_demo/` at the repository root rather than at the repository root directly, so it
does not mix with the course's own content (`exercise/`, `starter/`, `reference/`). All source
paths below are relative to `sdd_django_demo/`.

```text
sdd_django_demo/
└── api/
    ├── serializers.py      # new — signup input validation and output representation
    ├── views.py             # modified — signup endpoint alongside the existing health check
    ├── urls.py               # modified — route for signup
    └── test_signup.py        # new — written after implementation, from the specification
```

**Structure Decision**: Single project, single existing Django app. The existing `api` app (built
in the scaffold phase, currently serving only `/api/health/`) gains the signup endpoint; no new
Django app is introduced, because signup is one endpoint on an existing API surface and a second
app would add a settings change and an import path for no benefit.

## Design decisions

**No new model.** Django's built-in `User` already carries a unique `email` field and a hashed
`password` field. The specification (Key Entities) explicitly rules out a separate username, and
`User.username` is not part of this feature's contract — it is populated internally from the
normalised email (see below) purely so `create_user` has a value to store, and no code outside
account creation reads it.

**Email normalisation happens once, at the boundary.** FR-012 requires emails to be compared and
stored lowercase. Doing this in the serializer's `validate_email`, before any lookup or creation,
means every downstream consumer (the uniqueness check in FR-005, the `create_user` call in FR-007)
already sees the normalised value — there is exactly one place that lowercases an email, not one
per caller.

**Validation lives in a serializer, not the view.** FR-002 through FR-006, FR-010 and FR-012 are
all field-level statements, and DRF serializers already produce field-keyed error responses,
which is exactly the shape FR-010 requires.

**Password storage is delegated.** FR-008 is satisfied by creating the user through Django's
`create_user`, which applies the configured hasher. Nothing here implements hashing.

**Password exclusion is explicit.** FR-009 requires the password never appear in a response, so
the response is built from an output representation (`email` only, per FR-011) that has no
password field at all, rather than from the input serializer with the field suppressed.

**Password composition check is a serializer validator, not a Django `AUTH_PASSWORD_VALIDATORS`
entry.** FR-006's rule (8 characters, at least one letter and one digit) is specific to this one
endpoint, not a project-wide password policy statement, so it is expressed as a field validator on
`SignupSerializer` rather than a global setting that would also affect `createsuperuser` and the
admin site.

## Complexity Tracking

No constitutional violations requiring justification.
