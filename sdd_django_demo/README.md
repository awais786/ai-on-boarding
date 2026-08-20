# sdd_django_demo

A Django REST Framework API built through spec-driven development: every behavioural decision
starts as a written requirement, not a line of code. This README documents the process actually
used to build it — raw requirement through to implementation — not just how to run it.

## Running it

First time in this checkout — `.venv/` is gitignored, so it won't exist yet:

```bash
cd sdd_django_demo
make setup
```

Requires Python 3.12+ (Django 6.1's own floor; built and tested on 3.14). Then:

```bash
make run     # migrates and starts the dev server
make test    # pytest -v
make check   # manage.py check
```

`make setup` is just `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, and
each other target is a one-line wrapper around the equivalent `.venv/bin/python manage.py ...` /
`.venv/bin/pytest` command, if you'd rather run those directly — see `Makefile`.

- Health check: `GET /api/health/`
- API docs: `http://127.0.0.1:8000/api/docs/`
- OpenAPI schema: `http://127.0.0.1:8000/api/schema/`

## Setting up the planning tools

Implementing a change also needs the OpenSpec CLI (Node.js 20.19.0+ required):

```bash
npm install -g @fission-ai/openspec@latest
```

Verify with `openspec doctor` from the repo root — it should report `OpenSpec root: ok`. The
`/opsx:*` commands and `openspec-*` skills under `.claude/`/`.agents/` are already set up in this
repo; the CLI install above is the one thing that has to happen on your machine before they work.

## The process, step by step

This project runs on [OpenSpec](https://github.com/Fission-AI/OpenSpec). This project's rules
live in [`../openspec/config.yaml`](../openspec/config.yaml) — read that first; everything below
follows from it.

| Step | Command | Produces | Where it lives |
|---|---|---|---|
| 1. Raw requirement | — | a one-line product idea, deliberately under-specified | a GitHub issue |
| 2. Propose | `/opsx:propose "<idea>"` | `proposal.md` (why/what), a delta spec (requirements), `design.md` (how), `tasks.md` (checklist) — generated together | `openspec/changes/<name>/` |
| 3. Post to the issue | (manual, or `gh issue comment`) | the proposal and full delta spec, so the issue is self-contained | comments on the same GitHub issue from step 1 |
| 4. Review the proposal | (manual) | ambiguities resolved directly in the proposal/spec before any code exists | same files, edited in place |
| 5. Apply | `/opsx:apply` | working code, one `tasks.md` item at a time | `api/`, with `tasks.md` checkboxes updated as each task lands |
| 6. Test | (manual, after implementation) | tests written **from the spec**, not from the code | `api/test_*.py` |
| 7. Trace | (manual) | every requirement mapped to its task, code line and test | `openspec/changes/<name>/traceability.md` |
| 8. Review | `/code-review` | findings bound by the contract in `openspec/config.yaml` (see `CLAUDE.md`), ending in `Ready to merge: yes/no` | fixed and re-reviewed once (two passes max), then a pull request |
| 9. Archive | `/opsx:archive` | the change moved to `openspec/changes/archive/`, its delta spec merged into the canonical spec | `openspec/specs/<capability>/spec.md` |

Step 3 is required, not optional, per `openspec/config.yaml`'s `rules.tasks` — once all four
planning artifacts exist, a GitHub issue must exist for the change (create one via `gh issue
create` if it doesn't) and the proposal and delta spec get posted to it via `gh issue comment`.
It can't be enforced by the OpenSpec CLI itself (`operations` only hooks `apply` and `archive`,
not `propose`), so it's a documented rule agents are expected to actually follow, not a checked
gate — see issues [#9](https://github.com/awais786/ai-on-boarding/issues/9) and
[#10](https://github.com/awais786/ai-on-boarding/issues/10) for what it looks like done.

The chain each feature is checked against:

```
requirement "Reject a password shorter than 8 characters"  →  tasks.md item  →  api/serializers.py:18  →  test_signup_rejects_password_shorter_than_minimum
```

A requirement with no test is unverified behaviour. A test with no requirement is work nobody
asked for. A requirement with no code was never built. Steps 5–6 exist to catch all three.

## Starting a new feature (steps 1–2, concretely)

**If a GitHub issue already exists for the idea** (check first — don't assume there isn't one):
use its actual content as the input to `/opsx:propose`, don't paraphrase or write a fresh
description from scratch. Then link the resulting change back to *that* issue in step 3 — never
create a second issue for something that already has one.

**If no issue exists yet**: open one first, with the idea stated as a one-line, deliberately
under-specified requirement (see issue [#8](https://github.com/awais786/ai-on-boarding/issues/8)
for the shape). Then feed that issue's content into `/opsx:propose`.

Either way, the flow is:

```bash
gh issue view <number>              # read what's actually there
```
```
/opsx:propose "<the issue's content>"
```

then post the result back to the same issue (step 3), not a new one.

## After propose: steps 3–9, concretely

**3. Post to the issue.** Once `/opsx:propose` finishes, all four planning artifacts exist —
post `proposal.md` and the delta spec(s) as a comment on the issue from step 1:

```bash
gh issue comment <number> --repo awais786/ai-on-boarding --body-file <(cat proposal.md; echo; cat specs/*/spec.md)
```

Skip this and the issue is just a task list nobody can act on without cloning the repo — see
[#9](https://github.com/awais786/ai-on-boarding/issues/9) and
[#10](https://github.com/awais786/ai-on-boarding/issues/10) for what "done" looks like.

**4. Review the proposal.** Read `proposal.md` and the delta spec critically before any code
exists — this is the cheapest point to catch scope creep or an invented requirement. Fix it
directly in the files (`/opsx:update` can help reconcile artifacts if a fix in one place implies
a change elsewhere); don't wait to catch it in the diff later.

**5. Apply.**

```
/opsx:apply <change-name>
```

Works through `tasks.md` one item at a time, checking each box `[x]` as it lands. If it stops
partway, re-run the same command — it picks up from the first unchecked task.

**6. Test — from the spec, not from the code.** Once implementation tasks are done, list every
requirement in the spec and what a test would need to assert, *before* looking at the
implementation. Then write the tests, run them, and deliberately break something to prove at
least one test can actually fail — see `api/test_signup.py`'s dedicated race-condition regression
test for a concrete example of "prove it can fail" done for real, not just claimed.

**7. Trace.** Build `traceability.md` in the change folder: one row per requirement, mapping it
to its code location and its test — `| Requirement | Code | Test |`, nothing left blank. See
[`openspec/changes/archive/2026-08-19-add-user-signup/traceability.md`](../openspec/changes/archive/2026-08-19-add-user-signup/traceability.md)
for a real example — it existed during this project's earlier Spec Kit phase, was lost when that
work was migrated into OpenSpec, and was recreated on 2026-08-20 (its own note explains the gap).

**8. Review.**

```
/code-review <target>
```

Bound by the contract in `openspec/config.yaml` / `CLAUDE.md` — reads as blocking only if it
cites a requirement, a named failing test, or a documented convention; at most two passes; always
ends in an explicit `Ready to merge: yes` or `Ready to merge: no`. Fix what's blocking, re-run
once, then open the pull request.

**9. Archive.**

```
openspec archive <change-name>
```

(or `/opsx:archive <change-name>`). This checks task completion first — if any are unchecked, it
warns and asks for confirmation rather than silently archiving unfinished work (verified directly:
running it against a change at 0/19 tasks printed `19 incomplete task(s) found. Continue? (y/N)`
and stopped cleanly on "n"). Only proceed past that warning if the change is genuinely done —
`operations.archive.guidance` in `openspec/config.yaml` says explicitly: only archive once
`/code-review` has returned `Ready to merge: yes` and `pytest` passes for the whole project.

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
  [`traceability.md`](../openspec/changes/archive/2026-08-19-add-user-signup/traceability.md) in
  the archived change maps each one to its code and test.
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
- **Status**: not yet implemented. Planning (proposal, spec, design, tasks) is complete, so this
  is ready to start at step 5 of the process table above, not step 1 — run `/opsx:apply
  add-user-signin` to begin implementing it.

## Conventions this project follows

See [`../openspec/config.yaml`](../openspec/config.yaml) for the full list. The ones that shape
every feature above:

- Tests are written **after** implementation, from the specification — not test-driven
  development, and stated explicitly so `/opsx:propose` never generates test-writing tasks.
- Generated code is never hand-patched. When output is wrong, the proposal, spec, design, or a
  project skill is fixed instead, and the code is regenerated.
- Tasks live in each change's `tasks.md`, mirrored on the feature's GitHub issue for visibility.
