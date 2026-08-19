# Phase 7 — Change what you built

## What you'll do

Two changes to a finished feature, in escalating order.

**First**, change the password minimum from 8 characters to 12 — an existing requirement, given a
new value. **Then**, handle a feature request from your lead, which makes the specification
*grow* rather than merely change.

This is the payoff. Everything so far could be dismissed as elaborate ceremony for building
something once. This phase is about the other 95% of a system's life: changing it after it works.

Signup is finished, verified and in a pull request. That complete baseline is the point — it is
what makes the blast radius of each change exactly measurable.

## Time

About 1.75 hours.

## Before you start

Phase 6 complete: green suite, gap closed, traceability table current.

## Steps

### 1. Predict the blast radius — before touching anything

Write your prediction in `impact.md`. For a change from 8 to 12 characters, which artefacts
change?

- The specification — obviously
- The technical plan — does it mention the number?
- The tasks — does any task encode it?
- The tests — which ones, exactly? Name them.
- The code — which file, which line?
- The traceability table — which rows?

Commit to specific answers. Name files and test names. A vague prediction cannot be wrong, which
means it teaches nothing.

### 2. Change the specification first

Edit the requirement to 12 characters. **Nothing else yet.** Do not touch the test. Do not touch
the code.

### 3. Watch the tests fail for the right reason

```bash
.venv/bin/pytest -v
```

Most likely everything still passes — because the tests encode 8, and so does the code. They
agree with each other and both now disagree with the specification.

**Sit with that for a moment.** A fully green suite, and the software no longer does what the
specification says. This is why phase 5 insisted that passing tests are not verification. Nothing
in your tooling will tell you about this. Only the trace from specification to test will.

### 4. Propagate, in order

```
spec ✓ → plan → tasks → tests → code → verify
```

Ask Claude to carry the change through:

```
The specification now requires a minimum password length of 12 characters.
Update the plan, tasks, tests and implementation to match. Show me what changed
at each stage before moving to the next.
```

Then run:

```bash
.venv/bin/pytest -v
```

### 5. Prove the change is real

A test that was passing before your change must now fail against the *old* behaviour. Check it:
set the code back to 8 characters temporarily and run the suite. A test must fail. If none does,
the tests were never updated and the suite is lying again.

Restore:

```bash
git checkout -- .
```

### 6. Compare against your prediction

Open `impact.md` and mark what you got right and what you missed.

The usual miss is the traceability table, or a test whose name mentions "8". The second is worth
noticing — a test named `test_password_min_8_characters` is now permanently misleading even
though it passes. Names are part of the artefact.

### 7. Commit

```bash
git add .
git commit -m "Change password minimum from 8 to 12 characters"
git push
```

---

## Part two — a feature request

The change above modified a requirement that already existed. This one is different: your lead is
asking for behaviour the specification never covered. The specification does not change value —
it **grows**.

### 8. Read the request

By now your lead will have **opened an issue in your repository**. If there isn't one, ask before
continuing.

It will be short — a sentence or two, the way real requests arrive. It will not tell you the field
name, the type, the status code, or what the edge cases should do. **Those gaps are not an
oversight; they are the work.**

Leave the issue open until the change is merged, and reference it from your pull request. The
issue is where the request came from; your specification is where the decisions about it live.
Those are two different documents and the issue does not replace the spec — a requirement that
exists only in a GitHub comment is a requirement nobody will find in six months.

### 9. Decide whether it belongs here at all

Before touching anything, write down the answer to one question: **is this part of signup, or is
it a separate feature?**

Either answer can be defended. A request arriving after a feature is finished is very often scope
creep, and "not in this specification — here is why" is a legitimate, sometimes correct response.
What is not defensible is failing to notice there was a question.

Write your answer and your reason in `impact.md`.

### 10. Predict the blast radius, again

You did this for the password change. Do it again, and notice the shape is different — a new
requirement does not just alter existing artefacts, it adds rows to them.

Predict specifically:

- How many new requirements does the specification gain?
- Which tasks are new, and which existing ones change?
- How many new tests, and what does each assert?
- Does the request contract change? Then the OpenAPI schema changes too.
- Does the PR description still describe what this branch does?

### 11. Clarify before you build

The request is vague, so clarify it — the same work you did in phase 2, on a smaller surface.
List every question it leaves open, decide each, and write the decisions into the specification.

If a decision feels arbitrary, it probably is. Make it anyway, and record why. An arbitrary
decision written down beats a sensible one left in your head, because only the written one can be
tested.

### 12. Propagate, in order

```
specification → PR description → plan → tasks → tests → code → traceability → schema
```

Eight artefacts. **The two most often forgotten are the first and the second.** The classic
failure is updating the code and the tests, leaving a specification that describes software which
no longer exists and a pull request that describes the wrong feature.

Update *Change requests folded in* in your PR description: link the issue, and say what it
touched. Close the issue when the pull request merges, not before.

### 13. Verify

```bash
.venv/bin/pytest -v
```

Then check the generated schema at `/api/docs/` against the amended specification, exactly as in
phase 5. A new field on the request is a schema change, and a schema that still shows the old
contract is drift.

Break one of the new requirements and confirm a test fails. New requirements deserve the same
proof as old ones.

### 14. Compare against your prediction

Open `impact.md`. What did you miss?

The usual misses are the PR description, the schema, and the traceability table — all artefacts
that are nobody's obvious responsibility. Notice which of them you overlooked; that is your blind
spot, and it will be the same one next time unless you name it.

### 15. Commit

```bash
git add .
git commit -m "Add <the requested feature> from change request"
git push
```

## Done when

- [ ] `impact.md` holds a prediction you wrote *before* making the change
- [ ] The specification was edited first, alone
- [ ] You observed that a green suite can disagree with the specification
- [ ] Plan, tasks, tests and code have all been brought into line
- [ ] A test genuinely fails when the code is reverted to 8 characters
- [ ] `traceability.md` is current
- [ ] You have compared the outcome against your prediction

**Part two — the feature request:**

- [ ] The issue is referenced from your pull request, and still open until it merges
- [ ] You wrote down whether the request belonged in this specification, and why
- [ ] You predicted the blast radius before changing anything
- [ ] You clarified the request's ambiguities and recorded each decision
- [ ] The specification was updated **first**, before any code
- [ ] All eight artefacts moved: spec, PR description, plan, tasks, tests, code, traceability, schema
- [ ] A test for one of the new requirements fails when you break its code
- [ ] `pytest` passes and the schema matches the specification
- [ ] You compared the outcome against your prediction and named what you missed
- [ ] Your commits are in and pushed, so the pull request reflects them

## If it goes wrong

**Claude changed the code first and the specification last.** Revert and insist on the order.
The sequence is the lesson; the end state alone is not.

**Nothing failed at any point.** Then nothing was verifying that requirement. Go back to phase 5,
step 5, and fix the test so it can fail.

**The change turned out larger than predicted.** Good — that is the exercise working. Write down
what surprised you. A requirement that touches more places than expected is usually one that was
duplicated instead of being stated once.

**You think the feature request is scope creep.** Then say so, in writing, with your reasoning —
that is a legitimate answer, and a lead who gets it will usually respect it. But answer the
follow-up honestly too: if not now, then when, and what would have to be true first?

**The feature request feels too small to bother propagating properly.** It is exactly then that
the discipline matters. A one-line change that skips the specification leaves the document wrong
in a way nobody notices for months, because the code works fine.
