# Phase 2 — Constitution and specification

## What you'll do

Write the project's engineering principles, then turn a one-line product idea into a structured
specification — without saying how it should be built.

## Time

About 1.5 hours.

## Before you start

Phase 1 complete: `pytest` reports **1 passed** — not "no tests ran" — the health endpoint
returns 200, and there is no authentication code in the project.

## Steps

### 1. Start a branch for this feature

Everything from here until signup is merged belongs on one branch. Your lead reviews it as two
pull requests: the specification first, the implementation second.

```bash
git checkout -b feature/signup
```

Do this **before** writing the specification. If you write it on `main` and branch afterwards,
your first pull request will contain only whatever you changed after branching — and the
specification your lead is supposed to review will already be on `main`, invisible in the diff.

### 2. Create the constitution

```
/speckit-constitution
```

The constitution holds the rules by which every feature on this project gets built. It is not
about signup. It outlives signup.

Give it these principles, adding any you believe in:

```
Every behavioural requirement must have automated verification.
Security-sensitive behaviour must have explicit tests.
Follow existing Django and DRF conventions.
Prefer simple solutions over unnecessary abstractions.
Never modify a test merely to make a failing implementation pass.
Specifications may evolve when requirements change.
A change to the specification must be reflected in the affected plan, tasks, tests and code.
Code is generated from instructions, never hand-written. When generated code is wrong,
fix the instruction that produced it rather than the code itself.
Recurring technique belongs in a project skill, not in a prompt repeated each session.
Tests are written after the implementation exists, derived from the specification.
This project does not practise test-driven development.
```

That last pair is not stylistic preference — it is load-bearing. Spec Kit generates test tasks
*before* implementation whenever it concludes that tests were requested, and the first principle
in this list ("every behavioural requirement must have automated verification") reads exactly like
such a request. Stating the ordering explicitly is what stops your task list from arriving
test-first.

Read what it generates. Three of those lines carry most of the weight. *Never modify a test
merely to make a failing implementation pass* is what stops a green suite from becoming a lie.
*A change to the specification must be reflected in…* is what makes the specification a living
document rather than a discarded first draft. And *fix the instruction that produced it* is the
one you will actually be tested on — every time generated code is nearly right, it will be
quicker to patch the code than to work out which instruction was inadequate.

### 3. Specify the feature

```
/speckit-specify
```

Give it exactly this, and nothing more:

```
Build a user signup feature for the Django REST API. A user should be able to
create an account using a username, an email address and a password.
```

**Resist the urge to help.** Do not mention models, serializers, views, JWT, status codes, or
the database. Three fields is all the detail you give — everything about how they behave is for
clarification to draw out. That restraint is the entire lesson of this step: you are stating what the product
must do, and letting the *how* be decided later, in the open, where it can be reviewed.

### 4. Read what came back

Read the generated specification line by line. Expect it to have invented detail you never
supplied — that is normal and is exactly what the next step exists to catch.

As you read, keep one question running: **could two developers read this and build different
things?** Every place the answer is yes is something you will fix in phase 3.

### 5. Run clarification

```
/speckit-clarify
```

This surfaces ambiguities and asks you to resolve them. Answer as the person deciding what the
product should do — because for this exercise, you are.

You will not know the "right" answers to some of them. That is realistic. Make a decision,
and make it explicit. An arbitrary decision written down beats a sensible one left in someone's
head, because only the written one can be tested.

**The rule for this step:** resolve ambiguity in the specification, never in the code. If you
catch yourself thinking "I'll just handle that case when I implement it", stop — that thought is
the failure this whole exercise exists to prevent.

### 6. Find where everything landed

Spec Kit writes to fixed locations, and you will be opening these files constantly from here on:

| Artefact | Path |
|---|---|
| Constitution | `.specify/memory/constitution.md` |
| Specification | `specs/NNN-<short-name>/spec.md` |
| Quality checklist | `specs/NNN-<short-name>/checklists/requirements.md` |
| Plan (phase 4) | `specs/NNN-<short-name>/plan.md` |
| Tasks (phase 4) | `specs/NNN-<short-name>/tasks.md` |

`NNN` is a sequence number and `<short-name>` is generated from your description — `001-user-signup`
is typical. Spec Kit records the directory it chose in `.specify/feature.json`, so if you cannot
find it, read that file.

Open the specification now and keep it open. Phase 3 is nothing but reading it.

### 7. Commit

```bash
git add .
git commit -m "Add constitution and signup specification"
```

## Done when

- [ ] A constitution exists and includes the two rules about tests and about spec changes
- [ ] A signup specification exists, generated from the one-line idea
- [ ] You have run `/speckit-clarify` and answered its questions
- [ ] The specification still contains **no** Django-specific implementation detail — no model
      names, no serializer names, no view classes
- [ ] You are on the `feature/signup` branch, not `main`
- [ ] You know the path to your `spec.md`, and have opened it
- [ ] Your commit is in

If the last box fails, the specification has drifted into being a plan. Ask Claude to remove the
implementation detail and keep the behaviour.

## If it goes wrong

**The specification is full of Django detail.** Something in your prompt invited it. Say:
*"This specification describes implementation. Rewrite it to describe only externally observable
behaviour — what a caller of the API can see. Move anything about Django into a note for the
planning stage."*

**`/speckit-clarify` asks nothing, or asks trivia.** Push it: *"What behaviour does this
specification leave undefined? Consider the email field, the password field, duplicates, and what
a successful response contains."* You are allowed to prompt the tool that prompts you.

**You do not know what to answer.** Pick the simplest thing that is defensible and write it
down. Phase 7 is entirely about changing a requirement later — nothing you decide here is
permanent.
