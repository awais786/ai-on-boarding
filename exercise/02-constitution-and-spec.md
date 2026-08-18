# Phase 2 — Constitution and specification

## What you'll do

Write the project's engineering principles, then turn a one-line product idea into a structured
specification — without saying how it should be built.

## Time

About 1.5 hours.

## Before you start

Phase 1 complete: `pytest` passes, the health endpoint returns 200, and there is no
authentication code in the project.

## Steps

### 1. Create the constitution

```
/speckit.constitution
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
```

Read what it generates. Three of those lines carry most of the weight. *Never modify a test
merely to make a failing implementation pass* is what stops a green suite from becoming a lie.
*A change to the specification must be reflected in…* is what makes the specification a living
document rather than a discarded first draft. And *fix the instruction that produced it* is the
one you will actually be tested on — every time generated code is nearly right, it will be
quicker to patch the code than to work out which instruction was inadequate.

### 2. Specify the feature

```
/speckit.specify
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

### 3. Read what came back

Read the generated specification line by line. Expect it to have invented detail you never
supplied — that is normal and is exactly what the next step exists to catch.

As you read, keep one question running: **could two developers read this and build different
things?** Every place the answer is yes is something you will fix in phase 3.

### 4. Run clarification

```
/speckit.clarify
```

This surfaces ambiguities and asks you to resolve them. Answer as the person deciding what the
product should do — because for this exercise, you are.

You will not know the "right" answers to some of them. That is realistic. Make a decision,
and make it explicit. An arbitrary decision written down beats a sensible one left in someone's
head, because only the written one can be tested.

**The rule for this step:** resolve ambiguity in the specification, never in the code. If you
catch yourself thinking "I'll just handle that case when I implement it", stop — that thought is
the failure this whole exercise exists to prevent.

### 5. Commit

```bash
git add .
git commit -m "Add constitution and signup specification"
```

## Done when

- [ ] A constitution exists and includes the two rules about tests and about spec changes
- [ ] A signup specification exists, generated from the one-line idea
- [ ] You have run `/speckit.clarify` and answered its questions
- [ ] The specification still contains **no** Django-specific implementation detail — no model
      names, no serializer names, no view classes
- [ ] Your commit is in

If the last box fails, the specification has drifted into being a plan. Ask Claude to remove the
implementation detail and keep the behaviour.

## If it goes wrong

**The specification is full of Django detail.** Something in your prompt invited it. Say:
*"This specification describes implementation. Rewrite it to describe only externally observable
behaviour — what a caller of the API can see. Move anything about Django into a note for the
planning stage."*

**`/speckit.clarify` asks nothing, or asks trivia.** Push it: *"What behaviour does this
specification leave undefined? Consider the email field, the password field, duplicates, and what
a successful response contains."* You are allowed to prompt the tool that prompts you.

**You do not know what to answer.** Pick the simplest thing that is defensible and write it
down. Phase 7 is entirely about changing a requirement later — nothing you decide here is
permanent.
