# Facilitator guide

For whoever runs this exercise. Learners are told to read the clarification checklist only after
attempting it themselves in phase 3 — if you hand it over early, you remove the practice.

## The shape of the exercise

Three phases carry almost all the learning. If time is short, protect these and compress the rest.

| Phase | What it really teaches |
|---|---|
| 3 — Review the spec | That "passwords should be secure" is not a requirement |
| 4 — Implement and test | That a test written from the code asserts what the code does |
| 8 — Extend the skill | That a correction you had to make twice was a missing instruction |
| CR-1 / CR-2 | That a change request updates the specification, not the code |
| 5 — Verify and trace | That a generated schema is a second, checkable specification |
| 6 — When things are wrong | Code bug vs spec bug vs spec gap |
| 7 — Change what you built | That a green suite can disagree with the specification, and that a new requirement grows every artefact |

Phases 1, 2 and 4 are mechanics. They matter, but nobody's mental model changes there.

## Clarification checklist

The checklist itself now lives in [`../reference/clarification-checklist.md`](../reference/clarification-checklist.md),
because learners are told to compare against it in phase 3 and it must reach them without sending
them into this file — which would spoil the change requests, the phase 7 payoff and the assessment
strategy.

Use it yourself at gate 1: a specification that leaves any of those items unsettled is not ready
to be built from.

## Where learners get stuck

**Phase 1 — the scaffold diverges.** If Claude adds a custom user model or an auth app, later
phases get confusing because signup half-exists. Check for this before anyone moves on. The
scaffold spec puts it out of scope; hold the line.

**Phase 2 — implementation leaks into the specification.** Very common. The tell is a Django
class name in a document that should describe observable behaviour. Ask: *would a caller of the
API notice this?*

**Phase 1 — the skill does not load.** Skills are discovered at session start, so one copied in
mid-session will not appear. A restart fixes most cases; otherwise check the folder name matches
the `name:` in the frontmatter. Do not let anyone proceed without confirming Claude answers
project-specific questions from the skill rather than giving generic Django advice.

**Phase 4 — the break-it checkpoint gets skipped.** The most likely corner to be cut, and the
most damaging one. Tests are written after the implementation here, which means they have only
ever been observed passing against the very code they were written from. Until a learner has
broken the code and watched a specific test go red, that test is not yet evidence of anything.
The phase asks for three; check they did it. If they cannot say which three and what they broke,
they did not.

**Phase 4 — tests that only assert status codes.** The standard symptom of tests written by
reading the implementation rather than the specification. A requirement about behaviour verified
by `assert response.status_code == 400` is not verified. Have them ask what the requirement
would need the test to check, then compare.

**Phase 4 — tests fail and learners want to fix them immediately.** Let them sit. Phase 6 is
where diagnosis is taught, and a rushed fix teaches the opposite habit.

**Phase 5 — the traceability table gets filled in by asking Claude.** It defeats the purpose.
Learners may ask *where* something lives; they must write the rows themselves.

**Phase 6 — the gap is treated as a code bug.** The single most important correction you will
make. Undefined behaviour is not a defect in the code, because the code was never told. Push
until they see the difference.

**Phase 7 — the code gets changed first.** Revert and redo in order. The sequence is the lesson.

## The lead role

The exercise gates work through pull requests, twice per feature: **PR 1** on the specification
before anything is built, **PR 2** on the implementation. Someone has to review them.

Use `facilitator/lead-review-checklist.md`, and read `facilitator/review-contract.md` before
your first review. The two gates ask genuinely different questions, and reviewing gate 1 as
though it were code is the most common way to waste it — there is no code yet, and asking for
some misses the point.

**The contract exists because agent-assisted review does not terminate on its own.** Asked "is
this good?", a reviewer always finds something, and learners report reviews running to ten rounds
with fresh suggestions each time. The contract replaces that question with "does this meet the
specification?" — which has an answer. Only findings citing a requirement identifier, a named
failing test, or a documented convention may block; the finding list closes after round one; and
two rounds is the cap, after which the specification is what gets fixed.

If you review to your own instincts instead, the course teaches the opposite of what it says.

Learners are told to keep working while they wait, so you are not blocking them. But feedback
arriving after they have finished the whole feature teaches nothing about specification review.
**Aim for same working day.**

If someone is doing this alone, a fresh Claude Code session stands in, using the checklist for
gate 1 and `review-prompt.md` for gate 2. It is weaker — it will not argue with a product
decision — but it preserves the discipline of writing for a reader.

## Change requests

`facilitator/change-requests.md` holds two requests and when to fire them. **Learners must never
see that file.** Their materials say only that requests may arrive and what to do; the whole
value is that a real change request is unscheduled.

**Both requests land on finished features, never mid-build.** CR-1 goes out as they start phase
7, after signup is complete and they have done the password-minimum change. CR-2 goes out after
signin is finished in phase 8. A complete baseline is what makes the blast radius measurable —
and it is how change requests actually arrive.

**CR-1 is guided** — phase 7 part two walks them through it. **CR-2 is not**; phase 8 is where the
scaffolding comes off.

A learner who handles CR-1 well and CR-2 badly is producing the most useful signal in the whole
exercise: they can follow the motion but have not internalised it.

## Skills, and the no-hand-written-code rule

The scaffold ships `starter/skills/django-conventions/`, which learners copy into
`.claude/skills/` in phase 1. It encodes this project's layout, migration policy, auth rules and
test conventions, so generated code follows them without the learner re-explaining every session.

**The house rule is that learners do not hand-write code.** Enforce it. The rule is not purism —
it is what makes the exercise's central claim testable. If a learner patches generated code, the
instruction that produced the bad code is still wrong, and the next regeneration reintroduces it.
The correct move on every wrong output is *which instruction failed?*

Expect this to be broken quietly, usually when something is nearly right. The tell is a diff no
prompt could have produced. When you see it, do not treat it as cheating — ask which artefact
should have prevented it. That question is the lesson.

A skill is an **instruction artefact**, not code, so authoring one is fully consistent with the
rule. Learners edit the constitution, the specification and the skill; the agent produces
everything else. The glossary spells this out if anyone finds it confusing.

### The measurable bit

Phase 8 has learners extend the skill *before* attempting signin, from the corrections they had
to make during signup. Signin is a comparable feature, so if the skill genuinely improved, it
should need fewer corrections — and they are asked to record both counts.

This is the closest the exercise comes to an objective measure of whether someone understood the
point. A learner whose skill grew but whose correction count did not move has been writing down
what happened rather than what was missing. Worth a conversation.

Watch the length too. Skills load into context whenever they apply, so a bloated one costs on
every request and dilutes the rules that matter. Under a page is the target; a learner who has
written three pages has made things worse and should be asked to cut.

## Why Swagger is in here, and Postman is not

The scaffold ships `drf-spectacular`, so learners get `/api/schema/` and an interactive
`/api/docs/` from phase 1 onward. Two reasons, and only the second is really about teaching.

The plain one: the audience is fresh devs, and a **Try it out** button is far kinder than
composing curl by hand. It is used as the probing tool in phase 6.

The one that matters: the generated OpenAPI schema is **a second specification, derived from the
code**. Phase 5 has learners compare it against the specification they wrote. Drift becomes
visible by reading rather than by testing — a `password` field appearing in a response schema is
a specification violation you can spot in a browser, before any test exists to catch it. That is
a genuinely different verification instrument from the test suite, and worth naming as such when
you run the session.

Postman is deliberately not required. It is a nicer curl — it does not give you a second source
of truth, and it adds an import/export step and another install. Learners who prefer a GUI client
can use it instead of curl anywhere curl appears; nothing depends on it.

## The moment worth waiting for

Phase 7, step 3. The learner changes the specification to 12 characters, runs the suite, and it
is entirely green — because the tests and the code still agree with each other on 8.

Let that sit before explaining it. A green suite that disagrees with the specification is the
argument for traceability, and it lands far harder when they have just watched it happen than
when they are told it might.

## Timing

Roughly 14.25 hours of working time; two sessions, split after phase 5. Review waits sit on top,
but learners keep building through them, so they do not add to the total.

Phase 4 is about 2.5 hours and is the most variable — implementation runs from 30 minutes to 90
depending on how much the specification left open, and deriving tests from the specification
takes real thought on top. A vague specification is slower here, which is a useful thing for
learners to feel directly. Phase 5 runs closer to 1.25 hours with the schema comparison. A vague specification is slower here, which is a useful thing for
learners to feel directly.

## Prerequisites — what to enforce

Only these: Python 3.12+, git, a GitHub account, a terminal, Claude Code installed.

**Do not add Django to that list.** The exercise is designed so Django is the material, never the
subject. A learner who has never written a Django view can complete every phase — and having them
discover Django through a specification is closer to how they will actually work than a tutorial
would be.

## Assessment — verifying each learner's output

Every learner writes a different specification, so their implementations legitimately differ:
different password minimums, different status codes, different success payloads. You cannot run
one fixed test suite over the cohort and call the failures wrong.

Three layers, weakest to strongest.

### Layer 1 — the conformance suite (automated, uniform)

`facilitator/conformance/` checks only what must hold for **any** defensible signup and signin —
19 checks, asserting response *classes* (2xx / 4xx) rather than specific codes, with request
shapes taken from payloads you supply.

**Run it once, at submission, after both change requests are folded in.** Running it earlier
fails work that is correct for that moment, because the change requests add fields.

You must pass the learner's payloads, since change requests add fields whose names they chose:

```bash
cd facilitator/conformance
.venv/bin/pytest -v -rs \
  --signup-payload '{"username":"x","email":"x@example.com","password":"Str0ng!","accepted_terms":true}' \
  --signin-payload '{"username":"x","password":"Str0ng!"}'
```

One check reports rather than judges: whether signin by username survives the email change
request is the learner's documented backwards-compatibility decision, so the suite observes it
and you judge it against their spec. See `conformance/README.md`.

It deliberately does **not** check password storage, the schema, or code quality — those are
requirements in the learner's own specification, verified by their tests and by you at gate 2.
An automated security audit would imply a standard their spec does not contain.

**Hold this back until they submit.** A learner who has it will build to it instead of to their
own specification, which inverts the exercise.

### Layer 2 — the learner's own evidence

Phase 9 has them produce `SUBMISSION.md`: their decisions and reasons, their weakest test named
by them, one thing they would change, and proof they broke a requirement and watched its test
fail.

Read the "what I would change" and "where I am unsure" sections first. A submission claiming
everything is perfect deserves more scrutiny than one that names its own weak point.

### Layer 3 — review against *their* specification (the one that matters)

`facilitator/review-prompt.md`, run in a **fresh** Claude Code session in their repository. It
reports requirements with no implementation, requirements whose tests could not actually fail,
behaviour nobody specified, untestable requirements, and drift between spec and schema.

Layer 1 can only tell you they built *a* signup. Layer 3 tells you whether they built *the one
they specified* — which is the entire subject of the exercise.

### What the results actually tell you

| Finding | What it means | Send them back to |
|---|---|---|
| Requirement with no implementation | They never verified, only ran tests | Phase 5 |
| Test exists but cannot fail | The most common and most instructive failure | Phase 5, step 6 |
| Behaviour nobody specified | They did not read the diff | Phase 4 |
| Untestable requirement | Phase 3 was skipped in spirit | Phase 3 |
| Spec and schema disagree | Two sources of truth, nobody looked | Phase 5, step 5 |

### The three things worth more than any of it

1. Did they specify before building, without being told to?
2. Did they find an ambiguity the tooling did not raise?
3. When something broke, did they ask *which artefact is wrong* before fixing anything?
4. Did their skill improve from experience, and did that show up in fewer corrections?

The third is the one that matters. It is the habit the entire exercise exists to build, and no
automated check will ever measure it.

## Extensions, once the basics land

- GitHub Issues from tasks (`/speckit.taskstoissues`) — connects this to normal project workflow
- `/speckit.analyze` and `/speckit.checklist` for larger specifications
- A second developer reviewing someone else's specification before implementation — this is where
  ambiguity becomes undeniable, because two people genuinely read it differently
