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

This project runs on [OpenSpec](https://github.com/Fission-AI/OpenSpec), not GitHub's Spec Kit
(used earlier in this project's history, then removed — see *Why OpenSpec, not Spec Kit* below).
This project's rules live in [`../openspec/config.yaml`](../openspec/config.yaml) — read that
first; everything below follows from it.

| Step | Command | Produces | Where it lives |
|---|---|---|---|
| 1. Raw requirement | — | a one-line product idea, deliberately under-specified | the GitHub issue that started the feature |
| 2. Propose | `/opsx:propose "<idea>"` | `proposal.md` (why/what), a delta spec (requirements), `design.md` (how), `tasks.md` (checklist) — generated together | `openspec/changes/<name>/` |
| 3. Review the proposal | (manual) | ambiguities resolved directly in the proposal/spec before any code exists | same files, edited in place |
| 4. Apply | `/opsx:apply` | working code, one `tasks.md` item at a time | `api/`, with `tasks.md` checkboxes updated as each task lands |
| 5. Test | (manual, after implementation) | tests written **from the spec**, not from the code | `api/test_*.py` |
| 6. Trace | (manual) | every requirement mapped to its task, code line and test | `openspec/changes/<name>/traceability.md` |
| 7. Review | `/code-review` | findings bound by the contract in `openspec/config.yaml` (see `CLAUDE.md`), ending in `Ready to merge: yes/no` | fixed and re-reviewed once (two passes max), then a pull request |
| 8. Archive | `/opsx:archive` | the change moved to `openspec/changes/archive/`, its delta spec merged into the canonical spec | `openspec/specs/<capability>/spec.md` |

The chain each feature is checked against:

```
requirement "Reject a password shorter than 8 characters"  →  tasks.md item  →  api/serializers.py:18  →  test_signup_rejects_password_shorter_than_minimum
```

A requirement with no test is unverified behaviour. A test with no requirement is work nobody
asked for. A requirement with no code was never built. Steps 5–6 exist to catch all three.

## Why OpenSpec, not Spec Kit

This project used GitHub's Spec Kit (`.specify/`, `/speckit-*` commands, `specs/NNN-feature/`
directories) through signup's entire build — spec, plan, tasks, implementation, tests,
traceability, two-round review, all of it. On feedback, Spec Kit was removed entirely and
replaced with OpenSpec. Signup's Spec Kit artifacts were migrated into OpenSpec's format rather
than left behind or rebuilt from scratch — see
[`openspec/changes/archive/2026-08-19-add-user-signup/`](../openspec/changes/archive/2026-08-19-add-user-signup/)
for the migrated proposal/spec/design/tasks, now the canonical
[`openspec/specs/user-signup/spec.md`](../openspec/specs/user-signup/spec.md). Signin's
in-progress Spec Kit spec/plan was likewise translated into
[`openspec/changes/add-user-signin/`](../openspec/changes/add-user-signin/) before implementation
started, so no planning work was thrown away in the switch.

## Features built this way

### Signup — [issue #9](https://github.com/awais786/ai-on-boarding/issues/9)

- **Raw requirement**: "A user should be able to create an account by providing an email address
  and password" — from the original product requirement (signup + signin).
- **Spec**: [`openspec/specs/user-signup/spec.md`](../openspec/specs/user-signup/spec.md) — 12
  requirements, covering validation, duplicate rejection (including the concurrent-request race),
  password storage, and the response contract.
- **Change history**: [`openspec/changes/archive/2026-08-19-add-user-signup/`](../openspec/changes/archive/2026-08-19-add-user-signup/)
  — the archived proposal, design, and fully-checked tasks. Design: no new model (reuses
  Django's built-in `User`), validation in a serializer, password storage delegated to
  `create_user`.
- **Tasks**: mirrored on issue #9 as a checklist, each tagged with the requirement it satisfies.
- **Tests**: [`api/test_signup.py`](api/test_signup.py) — 14 tests covering every requirement.
  `traceability.md` in the archived change maps each one to its code and test.
- **Reviewed**: `/code-review` round 1 blocked on two findings — a check-then-create race in the
  duplicate-email rejection (concurrent signups for the same email could return an unhandled 500
  instead of a 400) and zero tests existing. Both fixed (the race via `transaction.atomic()` +
  catching `IntegrityError`; tests added, including a dedicated regression test for the race).
  Round 2 confirmed both fixes and found nothing new. **Ready to merge: yes.**
- **Status**: done — implemented, tested, traced, reviewed to a clean verdict, and archived.

### Signin — [issue #10](https://github.com/awais786/ai-on-boarding/issues/10)

- **Raw requirement**: "A registered user should be able to sign in using their credentials."
- **Spec**: [`openspec/changes/add-user-signin/specs/user-signin/spec.md`](../openspec/changes/add-user-signin/specs/user-signin/spec.md)
  — 14 requirements, the most consequential being that a wrong password and an unregistered
  email return an **identical** rejection, to prevent email enumeration.
- **Design**: [`openspec/changes/add-user-signin/design.md`](../openspec/changes/add-user-signin/design.md)
  — authenticates via Django's `authenticate()` (which already returns `None` uniformly for both
  failure cases, making the identical-rejection requirement fall out of the standard call rather
  than a hand-written special case), issues a DRF auth token, and introduces one new model
  (`SigninAttempt`) to track a 3-attempts/5-minute lockout — the one deliberate exception to
  signup's "no new model" precedent, justified in the design's Risks/Trade-offs section.
- **Tasks**: [`openspec/changes/add-user-signin/tasks.md`](../openspec/changes/add-user-signin/tasks.md),
  mirrored on issue #10.
- **Status**: not yet implemented.

## Conventions this project follows

See [`../openspec/config.yaml`](../openspec/config.yaml) for the full list. The ones that shape
every feature above:

- Tests are written **after** implementation, from the specification — not test-driven
  development, and stated explicitly so `/opsx:propose` never generates test-writing tasks.
- Generated code is never hand-patched. When output is wrong, the proposal, spec, design, or a
  project skill is fixed instead, and the code is regenerated.
- Tasks live in each change's `tasks.md`, mirrored on the feature's GitHub issue for visibility.
