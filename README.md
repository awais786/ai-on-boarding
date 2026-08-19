# Spec-Driven Development

A user signup and signin API, built without writing the code by hand.

That sentence is the whole point. Each feature starts as a written **specification** — a precise
description of how it must behave — and an AI coding agent turns it into Django code. The job is
to decide what the software should do, to say it precisely enough that it can be built and
tested, and to verify that what came back actually matches what was asked for.

This is called **spec-driven development**. The specification is the source of truth. Code
exists to satisfy it, and tests are the executable evidence that it does. The actual build —
`sdd_django_demo/` — documents this process end to end for both features in
[`sdd_django_demo/README.md`](sdd_django_demo/README.md).

## What actually happens

Six commands carry a feature from a one-line idea to reviewed, tested code. Each one reads the
artefact before it and writes the next, so nothing is ever built from a conversation someone
half-remembers.

| You run | It produces | You then |
|---|---|---|
| `/speckit-constitution` | `constitution.md` — the rules every feature obeys | Read it once; it outlives this feature |
| `/speckit-specify` | `spec.md` — requirements as `FR-001`, `FR-002`, … | Read every line and hunt for invented detail |
| `/speckit-clarify` | questions about what you left ambiguous | Decide, out loud, and let it write your answers in |
| `/speckit-plan` | `plan.md` — the technical approach | Check it against the constitution |
| `/speckit-tasks` | a dependency-ordered task breakdown, `T001`, `T002`, … | Check every `FR-` is covered by some task |
| a separate posting step (`gh issue create`/`gh issue comment`, or `/speckit-taskstoissues`) | that breakdown, posted to the feature's GitHub issue as a checklist | Track progress there, not in a file |
| `/speckit-implement` | working Django code | Then write tests **from the spec**, not from the code |
| — | `traceability.md` | Map every `FR-` to its code and test by hand — nothing generates this link for you |
| `/code-review` | findings bound by Constitution Principle XII, ending in an explicit verdict | Fix what's blocking, re-run for a second (and final) pass, then **open a pull request; your lead reviews spec, plan and code together** |

`/speckit-tasks` generates the breakdown; it does not talk to GitHub itself. Posting it to the
issue is a distinct step, and that issue — not a `tasks.md` file — is where task status lives
from then on; a file duplicating the issue gives nobody, human or agent, anything the issue
doesn't already have. Review happens as a single pull request per feature rather than a fixed
two-gate split; open it whenever the work is ready to be judged, which is usually once the spec,
plan and implementation are all in place.

`/code-review` is not optional theatre and it is not open-ended. `CLAUDE.md` (root and
`sdd_django_demo/`) points it at the constitution's review contract: a finding blocks only if it
cites an `FR-` ID, a named failing test, or a documented convention; it runs at most two passes
— an initial pass and one follow-up after fixes, never a third; and it always ends with
`Ready to merge: yes` or `Ready to merge: no`, stated plainly, never left as an open list. That
last part is what stops review from becoming the thing that never converges — see the signup
build in `sdd_django_demo/README.md` for a real example of both passes.

The chain is the thing to watch:

```
requirement FR-004  →  GitHub issue task T002  →  api/serializers.py:18  →  test_password_too_short_rejected
```

If any link is missing, something is wrong and the table is what shows you: a requirement with no
test is unverified behaviour, a test with no requirement is work nobody asked for, and a
requirement with no code was never built at all.

**Tests come after the implementation, deliberately.** This is not test-driven development. You
write tests from the specification once the code exists, which is harder than it sounds — the
temptation is to read the code and describe what it already does, and a test written that way
can never fail.

## What you will learn

Not Django. Django is the material, not the subject.

- **To write a requirement that can be tested.** *"Passwords should be secure"* cannot be. *"Passwords shorter than 8 characters are rejected with a 400 and a field-level error"* can. Telling those apart, reliably, is the core skill.
- **To spot what an agent invented.** Ask for three fields and you will get status codes, token strategies and validation rules you never mentioned. Some will be right. Deciding which is your job, and it is the job that does not go away.
- **To fix the instruction, not the output.** When generated code is nearly right, patching it by hand is faster and leaves the instruction still wrong. The next regeneration brings the bug back.
- **To change a finished feature properly.** A request arrives after signup is built and merged. You will edit the specification first and let the change propagate — spec, plan, tasks, tests, code — rather than reaching straight for the view.
- **To tell three kinds of wrong apart.** A code bug means the code disagrees with the spec. A spec bug means the spec says the wrong thing. A gap means nobody ever decided. Each has a different fix, and confusing them is how teams argue for a week.
- **To end a code review.** Reviews that never converge are reviews with no agreed standard. You will work under a contract where findings must cite a requirement, a failing test or a documented convention — and where `PASS` is an expected outcome, not a failure of diligence.

## The house rule

**You do not hand-write code.** Not the models, not the views, not the tests.

You write and edit *instructions* — the specification, the constitution, and a skill describing
how this project does Django. The agent turns those into code. That division is the whole point:
humans own intent, agents own implementation.

You will be tempted to break this, usually when something is nearly right and a two-line edit
would finish it. When you feel that, stop and ask a better question: **which instruction failed
to produce this?** Hand-editing the code fixes one symptom and leaves the instruction wrong, so
the next regeneration reintroduces the problem. Fix the instruction instead.

If you do end up editing code by hand — and occasionally you will — treat it as a finding worth
writing down, not a shortcut worth repeating.

## Who this is for

Developers who are new to Django, new to AI-assisted development, or both. Knowing Django,
Django REST Framework, or pytest going in isn't required — this project is set up so Django is
never the subject, it's the material spec-driven development is practised on.

**You do need:**

- Python 3.12 or newer installed (`python3 --version`)
- Git, and a GitHub account
- A terminal you are comfortable opening
- [Claude Code](https://docs.claude.com/en/docs/claude-code) installed
- **A lead** — someone who reviews the pull request before it merges. Working alone, a fresh
  Claude Code session can stand in, though it will not push back on a product decision the way a
  person will.

## What this repository contains

- A working Django REST API with a tested signup endpoint, and signin built the same way
- Interactive Swagger docs for it, usable to verify the API by hand and to check the generated
  schema against the specification
- A specification for each feature, precise enough to rebuild it from scratch
- A traceability table linking every requirement to the code and the test that satisfies it
- Evidence a reviewer can check against — including proof that at least one test per feature can
  actually fail
- A worked example of a feature request landing on a finished feature, propagated from the
  specification outward rather than patched into the code

See [`sdd_django_demo/README.md`](sdd_django_demo/README.md) for the concrete process each
feature went through, spec to code.

## The reading behind it

[`glossary.md`](glossary.md) defines every artefact — constitution, skill, specification, plan,
task, verification — in one place, along with the distinctions people most often blur. Skim it
now, and come back whenever a word stops making sense.

Facilitator material — a teaching guide, change requests, review checklists and a conformance
suite — lives on the `facilitator` branch.
