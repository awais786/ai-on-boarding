# sdd_django_demo

A Django REST Framework API built through spec-driven development: every behavioural decision
starts as a written requirement, not a line of code. This README documents the process actually
used to build it — raw requirement through to implementation — not just how to run it.

## Running it

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

```bash
.venv/bin/pytest -v
```

- Health check: `GET /api/health/`
- API docs: `http://127.0.0.1:8000/api/docs/`
- OpenAPI schema: `http://127.0.0.1:8000/api/schema/`

## The process, step by step

This project's rules live in [`.specify/memory/constitution.md`](../.specify/memory/constitution.md)
(one level up, at the repo root) — read that first; everything below follows from it.

Each feature goes through the same six steps. `sdd_django_demo/` never sees `tasks.md`: per
Constitution Principle XI, tasks are posted straight to the feature's GitHub issue instead of a
file, because a local file duplicating the issue gave nobody — human or the implementation step —
anything the issue didn't already have.

| Step | Command | Produces | Where it lives |
|---|---|---|---|
| 1. Raw requirement | — | a one-line product idea, deliberately under-specified | the GitHub issue that started the feature |
| 2. Specify | `/speckit-specify` | `spec.md` — requirements as `FR-001`, `FR-002`, … | `specs/<NNN-feature>/spec.md` |
| 3. Clarify | `/speckit-clarify` | ambiguities resolved, one question at a time, recorded in the spec | `spec.md`, `## Clarifications` section |
| 4. Plan | `/speckit-plan` | the technical approach, and why each decision was made | `specs/<NNN-feature>/plan.md`, `research.md`, `data-model.md`, `contracts/` |
| 5. Tasks | `/speckit-tasks` | a dependency-ordered checklist, each task tagged with the `FR-` it satisfies | posted directly to the feature's GitHub issue |
| 6. Implement | `/speckit-implement` | working code, generated from the tasks | `api/` |
| 7. Test | (manual, after implementation) | tests written **from the spec**, not from the code | `api/test_*.py` |
| 8. Trace | (manual) | every `FR-` mapped to its task, code line and test | `specs/<NNN-feature>/traceability.md` |
| 9. Review | `/code-review` | findings bound by Constitution Principle XII (see `CLAUDE.md`), ending in `Ready to merge: yes/no` | fixed and re-reviewed once (two passes max), then a pull request |

The chain each feature is checked against:

```
requirement FR-004  →  GitHub issue task  →  api/serializers.py:18  →  test_password_too_short_rejected
```

A requirement with no test is unverified behaviour. A test with no requirement is work nobody
asked for. A requirement with no code was never built. Steps 7–8 exist to catch all three.

## Features built this way

### Signup — [issue #9](https://github.com/awais786/ai-on-boarding/issues/9)

- **Raw requirement**: "A user should be able to create an account by providing an email address
  and password" — from the original product requirement (signup + signin).
- **Spec**: [`specs/001-user-signup/spec.md`](../specs/001-user-signup/spec.md) — 12 requirements,
  3 clarifications resolved (password rule, response shape, email normalisation).
- **Plan**: [`specs/001-user-signup/plan.md`](../specs/001-user-signup/plan.md) — no new model
  (reuses Django's built-in `User`), validation in a serializer, password storage delegated to
  `create_user`.
- **Tasks**: posted to issue #9 as a checklist, each tagged with its `FR-`.
- **Tests**: [`api/test_signup.py`](api/test_signup.py) — 14 tests covering FR-001 through
  FR-012. [`specs/001-user-signup/traceability.md`](../specs/001-user-signup/traceability.md)
  maps every requirement to its code and test.
- **Reviewed**: `/code-review` round 1 blocked on two findings — a check-then-create race in the
  duplicate-email rejection (concurrent signups for the same email could return an unhandled 500
  instead of a 400) and zero tests existing. Both fixed (the race via `transaction.atomic()` +
  catching `IntegrityError`; tests added, including a dedicated regression test for the race).
  Round 2 confirmed both fixes and found nothing new. **Ready to merge: yes.**
- **Status**: done — implemented, tested, traced, and reviewed to a clean verdict.

### Signin — [issue #10](https://github.com/awais786/ai-on-boarding/issues/10)

- **Raw requirement**: "A registered user should be able to sign in using their credentials."
- **Spec**: [`specs/002-user-signin/spec.md`](../specs/002-user-signin/spec.md) — 14 requirements,
  3 clarifications resolved, the most consequential being that a wrong password and an
  unregistered email return an **identical** rejection (FR-008), to prevent email enumeration.
- **Plan**: [`specs/002-user-signin/plan.md`](../specs/002-user-signin/plan.md) — authenticates via
  Django's `authenticate()` (which already returns `None` uniformly for both failure cases,
  making FR-008 fall out of the standard call rather than a hand-written special case), issues a
  DRF auth token, and introduces one new model (`SigninAttempt`) to track a 3-attempts/5-minute
  lockout — the one deliberate exception to signup's "no new model" precedent, justified in the
  plan's Complexity Tracking table.
- **Tasks**: posted to issue #10 as a checklist.
- **Status**: not yet implemented.

## Conventions this project follows

See [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) for the full list.
The ones that shape every feature above:

- Tests are written **after** implementation, from the specification — not test-driven
  development, and stated explicitly so `/speckit-tasks` never generates test-first tasks.
- Generated code is never hand-patched. When output is wrong, the specification, plan, or a
  project skill is fixed instead, and the code is regenerated.
- Tasks live on the feature's GitHub issue, not a `tasks.md` file.
