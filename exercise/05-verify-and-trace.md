# Phase 5 — Verify and trace

## What you'll do

Run the tests, then do the thing that tests cannot do for you: check that they verify what the
**specification** says, and build a table linking every requirement to the code and test that
satisfy it.

A green suite proves the code does what the tests say. It says nothing about whether the tests
say what you asked for.

## Time

About 1 hour.

## Before you start

Phase 4 complete: an implementation you have read the diff of, tests written from the
specification, and three of them proven able to fail.

## Steps

### 1. Run the suite

```bash
.venv/bin/pytest -v
```

Read the test names. They should sound like your requirements. If a test is called
`test_signup_works`, that is a smell — it tells you nothing about which behaviour is protected.

### 2. Build the traceability table

Create `traceability.md`. One row per requirement in your specification, using **the identifiers
from the specification itself** — not a fresh numbering you invent here. If the two ever diverge,
the table stops being a reference and becomes a second, competing document.

| # | Requirement | Task | Code | Test |
|---|---|---|---|---|
| FR-001 | Signup requires an email | T002 | `api/serializers.py:14` | `test_signup_requires_email` |
| FR-002 | Signup requires a password | T002 | `api/serializers.py:18` | `test_signup_requires_password` |
| FR-003 | Invalid email is rejected | T002 | … | … |
| FR-004 | Password shorter than the minimum is rejected | … | … | … |
| FR-005 | Duplicate email is rejected | … | … | … |
| FR-006 | A valid request creates exactly one user | … | … | … |
| FR-007 | The password is stored hashed, never in plain text | … | … | … |
| FR-008 | The password is never returned in a response | … | … | … |
| FR-009 | A successful signup returns the specified status | … | … | … |

Use **your** requirements and **your** identifiers, not these — this is the shape, not the
content. Every identifier in this table must exist in the specification, and every requirement in
the specification must appear here.

**Expect to do the Task column by hand.** Spec Kit labels tasks by user story, not by requirement
identifier, so nothing in `tasks.md` tells you that `T002` satisfies `FR-001`. You work it out by
reading the task and the requirement side by side. That is tedious, and it is also the entire
exercise: the gap you are about to find exists precisely because no tool was maintaining this
link for you.

Fill it in yourself, by looking. You may ask Claude where something lives (*"which line validates
the email?"*), but you write the row, because the point is that you can trace it.

### 3. Find the holes

Three failure modes, and the table makes each one visible:

- **An identifier in the table that is not in the specification.** Either you invented a
  requirement while building, or the spec was renumbered underneath you. Both are worth knowing.
- **A requirement with no test.** Unverified behaviour. It may work today and silently break
  tomorrow, and nothing will tell you.
- **A test with no requirement.** Either an undocumented requirement — write it down — or a test
  asserting something nobody asked for.
- **A requirement with no code.** It was never built. The suite is green because nothing checks it.

### 4. Check the tests actually test the requirement

Take FR-007 — the password is stored hashed. Open its test. Does it assert the stored value differs
from the submitted password, or does it merely assert the request returned 201?

This is the difference between a test and a passing test. Do this for at least three rows,
choosing the ones that would hurt most if wrong.

### 5. Check the API against its own generated schema

You now have two specifications, and this is the moment to notice it.

- The one **you wrote** — the source of truth, describing what signup must do.
- The one **generated from your code** — the OpenAPI schema at `/api/schema/`, describing what
  signup actually does.

They should agree. Where they do not, something has drifted, and you can see it without running
a single test.

Start the server and open **http://127.0.0.1:8000/api/docs/**. Find the signup endpoint and read
its schema — the request body, the response bodies, the status codes.

Now compare it against your specification, line by line:

- Does the request body show exactly the fields you specified — no more?
- Do the documented status codes match the ones you specified?
- Does the success response contain what you said it would?
- **Does `password` appear anywhere in a response schema?** If it does, you have found a
  specification violation by reading a web page, before any test ran.

Use **Try it out** to send a real signup request and see the live response next to the documented
one. A schema that promises 201 while the endpoint returns 200 is drift too.

Record anything you find. A mismatch here is a genuine defect — decide in phase 6 whether it is a
code bug, a spec bug, or a gap.

### 6. Prove the rest of the tests can fail

In phase 4 you proved three tests could fail. Those were the ones you were most worried about.
Now do the remainder — because a test that has only ever been seen passing is not yet evidence
of anything.

Work through the traceability table row by row. For each requirement you have not already
checked: break the code that satisfies it, run the suite, confirm the matching test fails,
restore.

**The relevant test must fail.** If everything still passes, that test does not protect that
requirement, and you have found a real defect in your verification.

Undo the break:

```bash
git checkout -- .
```

### 7. Open PR 2 — the implementation

```bash
git add .
git commit -m "Add signup traceability and verification"
git push
```

Open a pull request titled **`Implement signup`**. The template's *The plan* section is the one
that matters: a reviewer should be able to judge your approach from it without opening the diff.
Paste in the technical plan from phase 4, edited down to what a reader actually needs.

Leave *Change requests folded in* empty for now. You will come back to it.

### 8. Commit and push

```bash
git add traceability.md
git commit -m "Add requirement traceability"
git push
```

From here on, **every phase ends with a push.** Your pull request is what your lead reviews, and
a commit that never leaves your machine is invisible to them. A stale pull request is worse than
no pull request: they will review an implementation that predates everything you changed after it.

## Done when

- [ ] `pytest` passes
- [ ] `traceability.md` has a row for every requirement in the specification
- [ ] Every identifier in the table exists in the specification, and vice versa
- [ ] No requirement has an empty Test column
- [ ] No test exists that serves no requirement
- [ ] You have checked at least three tests actually assert the behaviour, not just a status code
- [ ] You have compared the generated OpenAPI schema against your specification, and confirmed
      `password` appears in no response schema
- [ ] You have broken one requirement's code and watched its test fail
- [ ] The break is reverted and the suite is green again
- [ ] PR 2 is open, titled `Implement signup`, and its plan section stands on its own

## If it goes wrong

**A requirement has no test.** Ask for one, naming the behaviour: *"Add a test asserting the
stored password is not the plain-text value submitted."* Then break the code to confirm the new
test can fail.

**You broke the code and nothing failed.** The most valuable thing that can happen in this phase.
The test is asserting the wrong thing — usually a status code instead of the behaviour. Fix the
test, then break the code again to prove the fix.

**Tests fail and you cannot tell whether the code or the test is wrong.** That is exactly phase
6. Go there.

**The generated schema is vague — everything is just `object`.** DRF infers the schema from your
serializers, so a thin or missing serializer produces a thin schema. That is itself a finding:
ask Claude *"why is the signup request body untyped in the OpenAPI schema?"* and read the answer
before changing anything.
