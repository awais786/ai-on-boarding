# Spec-Driven Development — a hands-on exercise

You will build a user signup API without writing the code yourself.

That sentence is the whole point. You will write a **specification** — a precise description
of how signup must behave — and an AI coding agent will turn it into Django code. Your job is
to decide what the software should do, to say it precisely enough that it can be built and
tested, and to verify that what came back actually matches what you asked for.

This is called **spec-driven development**. The specification is the source of truth. Code
exists to satisfy it, and tests are the executable evidence that it does.

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

Developers who are new to Django, new to AI-assisted development, or both. You do **not**
need to know Django, Django REST Framework, or pytest before starting. You will pick up
enough of each along the way, and the exercise is designed so that Django is never the
subject — it is the material you practise on.

**You do need:**

- Python 3.12 or newer installed (`python3 --version`)
- Git, and a GitHub account
- A terminal you are comfortable opening
- [Claude Code](https://docs.claude.com/en/docs/claude-code) installed — `exercise/00-setup.md` walks you through it
- **A lead** — someone who reviews your pull requests. Your work is gated twice: once on the
  specification before anything is built, and once on the implementation. If you are working
  alone, a fresh Claude Code session can stand in, though it will not push back on a product
  decision the way a person will.

## How long this takes

About **14.25 hours**. That is not a single sitting.

| Phase | File | Time |
|---|---|---|
| 0 | [Setup](exercise/00-setup.md) | ~45m |
| 1 | [Build the scaffold](exercise/01-scaffold.md) | ~1h |
| 2 | [Constitution and specification](exercise/02-constitution-and-spec.md) | ~1.5h |
| 3 | [Review the specification](exercise/03-review-the-spec.md) | ~1h |
| 4 | [Plan, tasks, implement, test](exercise/04-plan-tasks-implement.md) | ~2.5h |
| 5 | [Verify and trace](exercise/05-verify-and-trace.md) | ~1.5h |
| | *— natural break —* | |
| 6 | [When something is wrong](exercise/06-when-things-are-wrong.md) | ~1h |
| 7 | [Change what you built](exercise/07-change-a-requirement.md) | ~1.75h |
| 8 | [Do it yourself: signin](exercise/08-signin-yourself.md) | ~2.75h |
| 9 | [Submit your work](exercise/09-submit-your-work.md) | ~30m |

Those figures are your working time. Reviews are asynchronous — you keep building while your
lead reads, so waiting does not add to them.

**Split it across two sessions, breaking after phase 5.** By then signup works and is verified.
Phases 6 to 8 are where the ideas actually land, and they deserve a fresh head.

## How to work through it

Do the phases in order. Each one opens with what the previous phase must have produced, and
closes with a **Done when** list you can check by yourself. Do not move on until you can tick
every box — later phases assume the earlier ones really worked.

If you get stuck, each file ends with an **If it goes wrong** section. Try that before asking
anyone.

## What you will end up with

- A working Django REST API with a tested signup endpoint, and then signin
- Interactive Swagger docs for it, which you will use to verify the API by hand and to check the
  generated schema against your own specification
- A specification that describes it precisely enough to rebuild it from scratch
- A traceability table linking every requirement to the code and the test that satisfy it
- A reusable Django skill you extended yourself, which made the second feature faster than the
  first
- Evidence you can hand to a reviewer — including proof that at least one of your tests can
  actually fail
- Experience of a feature request landing mid-build, and of propagating it from the specification
  outward rather than patching the code
- Direct experience of the three reasons software is wrong — a code bug, a spec bug, and a
  gap where nobody ever decided

## The reading behind it

[`glossary.md`](glossary.md) defines every artefact — constitution, skill, specification, plan,
task, verification — in one place, along with the distinctions people most often blur. Skim it
now, and come back whenever a word stops making sense.

If you are going to **teach** this rather than take it, you want `facilitator/` — it carries the
reasoning behind the sequence, where learners get stuck, and how their work is verified. If you
are taking the course, do not read it: it spoils several things the exercise depends on you
discovering.
