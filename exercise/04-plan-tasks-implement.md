# Phase 4 — Plan, tasks, implement, test

## What you'll do

Turn the approved specification into a technical plan, break it into tasks, let Claude implement
it, then write the tests that verify it.

Django finally enters the conversation here — and notice how late that is.

## Time

About 2.5 hours.

## Before you start

Phase 3 complete: a reviewed specification where every requirement can fail, you have approved
it, and PR 1 is open with your lead.

You are working on the `feature/signup` branch. Keep going while the lead reads — you are not
blocked.

**Feedback may arrive while you work.** When it does, treat it as what it is: a change to the
specification. Update the specification first, then let the change flow through the plan, the
tasks, the tests and the code. Do not patch the code and leave the specification describing
something else.

## Steps

### 1. Create the technical plan

```
/speckit-plan
```

Now — and only now — supply the technical constraints:

```
Implement this feature using Django REST Framework, with pytest and pytest-django
for tests. Follow the conventions already in this project.
```

The plan may now talk about everything the specification was forbidden from mentioning:
application structure, the user model, serializers, views, URLs, validation, password storage,
and the testing strategy.

Read it, looking for one thing above all: **does every decision here trace back to a
requirement?** A plan that introduces behaviour the specification never asked for is scope creep,
and it is far cheaper to catch now than after it is code.

### 2. Generate tasks

```
/speckit-tasks
```

You should get something shaped like:

```
T001 [US1] Configure the authentication application
T002 [US1] Implement signup validation
T003 [US1] Implement user creation
T004 [US1] Implement the signup endpoint
T005 [US2] Return field-level errors on rejection
```

Two things about that output are worth knowing before you read it.

**Tasks are labelled by user story, not by requirement.** The `[US1]` tag points back to a user
story in your specification, and nothing in `tasks.md` says which `FR-` identifiers a task
satisfies. Working that out is your job, in phase 5, by reading the task and the requirement side
by side.

**There will be no test tasks, and that is correct here.** Spec Kit generates them only when the
specification asks for tests or you request a test-driven approach. Do neither. You write the
tests yourself in step 5, from the specification — and if Spec Kit writes them first, from the
plan, you lose the entire point of that step. If test tasks do appear, say *"remove the test
tasks — I am writing the tests myself after implementation"* and regenerate.

Then read them with one question: **which requirement does each task serve?** If a task serves
none, challenge it. If a requirement has no task, that is a gap — say so and have the tasks
regenerated.

A task is work to be done and will be finished forever. A requirement is a statement about
behaviour that stays true for the life of the feature. `T003 — implement user creation` will be
ticked off; *"a successful signup creates exactly one user"* stays true for the life of the
feature.

### 3. Implement

```
/speckit-implement
```

Then watch. This will take a while and touch several files.

Notice what is different from ordinary AI coding. Claude has not been told *"build me a signup
API"* — it has a constitution, a reviewed specification, a technical plan and a task list, and
those artefacts constrain what it is allowed to produce.

### 4. Read the diff

```bash
git diff
```

Read it. Not to approve every line — you are new to Django — but with three questions in mind:

- Are there files you did not expect?
- Is there behaviour here that no requirement asked for?
- Is anything in the specification obviously missing from the code?

Ask Claude about anything you do not recognise. *"What does this serializer do?"* is a good
question and costs you nothing.

### 5. Write the tests — from the specification, not from the code

The code exists now, which creates a specific hazard worth naming.

**A test written by reading the implementation tends to assert what the implementation does.**
If the code returns 200 where your specification said 201, a test written from the code will
happily assert 200 — and pass forever, while the software quietly disagrees with its own
specification. The test confirms rather than verifies, and you cannot tell the difference by
looking at a green suite.

So work from the specification. Start by listing what must be tested, before writing any test
code:

```
List every requirement in the specification, one line each. For each, state what a
test would have to assert to catch a violation. Work only from the specification —
do not read the implementation for this step.
```

Read that list against your specification and fix anything missing. Then:

```
Now write the tests for that list. Name each test after the behaviour it protects,
not after the function it calls. If any test cannot be written against the current
implementation, tell me which and why rather than weakening the assertion.
```

That last clause matters. If a test cannot be written as the requirement demands, you have found
a real disagreement between the specification and the code — and you want it reported, not
quietly softened into something that passes.

### 6. Run them

```bash
.venv/bin/pytest -v
```

Read the test names. They should sound like your requirements. `test_signup_works` is a smell —
it tells you nothing about which behaviour is protected.

### 7. Prove the tests can actually fail

**This is the step that makes the previous two mean anything, and it is not optional.**

A test written after the code has no proof it can fail. It has only ever been observed passing,
against the very implementation it was written from. Until you have seen a test go red, you do
not know it is testing anything at all.

So make three of them fail on purpose. Choose the requirements you would least like to be wrong —
password storage, duplicate rejection, the minimum length are good candidates.

For each: break the code that satisfies it, run the suite, confirm **that specific test** fails,
then restore.

```bash
# break something — change the minimum length, delete a validator
.venv/bin/pytest -v
# confirm the right test failed, then:
git checkout -- .
```

If you break a requirement and the suite stays green, that test does not protect it. Fix the test
and break the code again to prove the fix. Phase 5 pushes this further across every requirement;
three is enough here to catch the worst of it early.

### 8. Commit

```bash
git add .
git commit -m "Implement signup from specification, with tests"
```

## Done when

- [ ] A technical plan exists and every decision in it traces to a requirement
- [ ] A task list exists and every requirement is covered by at least one task
- [ ] `/speckit-implement` has run to completion
- [ ] You have read the diff and asked about anything unfamiliar
- [ ] You listed what to test **from the specification** before writing test code
- [ ] Tests exist and are named after behaviours, not functions
- [ ] `pytest` passes
- [ ] You have broken the code for **three** requirements and watched the matching test fail
      each time
- [ ] Everything is restored and the suite is green
- [ ] You hand-wrote no code; anything you did edit by hand is written down as a finding
- [ ] Your commit is in

## If it goes wrong

**You broke a requirement and nothing failed.** The most valuable thing that can happen in this
phase. That test is asserting the wrong thing — usually a status code where the requirement is
about behaviour. Fix it, then break the code again to prove the fix.

**The tests only check status codes.** Common when tests are written from the code. Say:
*"These tests assert status codes. The specification is about behaviour — rewrite them to assert
what changed, not just what came back."*

**A test cannot be written as the requirement demands.** Do not weaken it. You have found a
disagreement between specification and implementation — which is a phase 6 question about which
of the two is wrong.

**You want to hand-edit the generated code.** The house rule says no, and the reason is
practical rather than purist: the code is an output. Patch it and the instruction that produced
it is still wrong, so the next regeneration brings the problem back. Work out which artefact
failed — the specification was ambiguous, the skill did not cover this case, the plan chose
badly — fix that, and regenerate. If you genuinely cannot find the responsible instruction,
write down what you had to hand-edit and why; that note is worth more than the edit.

**The plan invents features.** Say: *"The specification does not require X. Remove it from the
plan, or tell me which requirement you think it satisfies."* Making it justify the addition is
usually enough.

**Implementation stopped partway.** Ask which task it reached and have it continue: *"Continue
from T004."* The task list is what makes resuming cheap.

**It changed the specification while implementing.** Serious — it inverts the direction of
authority. Revert the specification and say: *"The specification is the source of truth. If it is
wrong, tell me and I will decide. Do not edit it while implementing."*
