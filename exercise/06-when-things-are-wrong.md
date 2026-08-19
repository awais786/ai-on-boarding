# Phase 6 — When something is wrong

## What you'll do

Learn the single most useful distinction in spec-driven development: when something is broken,
**what kind of broken is it?**

Three answers, three different responses. Choosing wrongly is how specifications rot.

## Time

About 1 hour.

## Before you start

Phase 5 complete: a green suite and a filled-in traceability table.

## The three cases

### Case A — a code bug

The specification is right, the test is right, the code is wrong.

```
SPEC ✓    TEST ✓    CODE ✗
```

*The specification says passwords must be at least 8 characters. The API accepts a 5-character
password.*

**Fix the code.** Do not touch the specification, and do not touch the test. Then run the suite
and verify again.

This case is the easy one, and it is also the one people get wrong under pressure — by editing
the test until it passes. Your constitution forbids that for a reason: a test changed to match
broken code converts a caught bug into a permanent lie.

When a test and an implementation disagree, neither one settles it. Go to the **specification** —
that is what the test was written from, and it is the only thing here with the authority to say
which of the two is wrong.

### Case B — a spec bug

The specification says the wrong thing. The code faithfully implements it.

*The specification requires 8 characters. Security has decided the minimum must be 12.*

Nothing is broken in the code — it did exactly what it was told. The **requirement** was wrong.

**Change the specification first**, then let the change propagate:

```
spec → plan → tasks → tests → code → verify
```

Fixing the code and leaving the specification at 8 is the single most damaging thing you can do
in this workflow. It makes the document lie, and every future decision made from it inherits
the lie.

### Case C — a spec gap

The behaviour was never defined at all.

*`User@example.com` signs up after `user@example.com` already exists. What should happen?*

Nobody decided. So the code did *something* — and whatever it did is neither right nor wrong,
because there was no standard to measure it against.

This is **not automatically a code bug**, and that is the insight worth carrying out of this
phase. The instinct is to "fix" it. But you cannot fix code that was never told what to do —
you can only decide, write the decision down, and then build to it:

```
find the gap → decide → update the spec → add a test → update the code → verify
```

## Lead feedback is one of these three

Your lead's review comments are not a fourth category. Every one of them is a code bug, a spec
bug, or a gap — and working out which comes before doing anything about it.

| The lead says | Usually means | You change |
|---|---|---|
| "This does not match the spec" | Code bug | The code |
| "That requirement is wrong" | Spec bug | The specification, then everything downstream |
| "What happens if…?" | Gap | Decide, write it into the spec, then build to it |

The third is the most common at gate 1, and the one people mishandle — a question is not a defect
report. It means nobody decided, and the answer belongs in the specification.

## Steps

### 1. Create a code bug and fix it correctly

Change the code so it accepts a password shorter than your specified minimum.

Run the suite. Confirm the relevant test fails. Now fix it — **in the code**, leaving spec and
test untouched. Run again.

### 2. Feel the wrong instinct

Break the same code again. This time ask Claude:

```
This test is failing. Make it pass.
```

Watch carefully. If it edits the *test* rather than the code, you have just seen the failure your
constitution exists to prevent, and you should stop and say so:

```
Do not change the test. The specification requires the minimum length. Fix the code.
```

Revert everything before moving on:

```bash
git checkout -- .
```

### 3. Find a real gap

Time to poke at the running API and see what nobody decided.

Start the server and open **http://127.0.0.1:8000/api/docs/**. Find signup, hit **Try it out**,
and send a request. Then send it again with the email's capitalisation changed. Swagger UI shows
you the status and body of each — which makes this faster than curl, and much easier to read.

The same thing from the terminal, if you prefer it:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/signup/ \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "correct-horse-battery"}'

curl -X POST http://127.0.0.1:8000/api/auth/signup/ \
  -H "Content-Type: application/json" \
  -d '{"email": "User@example.com", "password": "correct-horse-battery"}'
```

Now open your specification and look for the rule that says what should happen. If it is not
there, you have found a genuine gap in your own work — and you found it the way gaps are always
found, by trying something nobody thought about.

### 4. Close the gap in the right order

1. Decide. (Emails are usually treated case-insensitively for uniqueness. Decide deliberately.)
2. Write it into the **specification**.
3. Add a test for it.
4. Update the code.
5. Run the suite, re-check `/api/docs/` still matches the specification, and update
   `traceability.md` with the new row.

Notice the order. The code changed fourth, not first.

### 5. Commit

```bash
git add .
git commit -m "Close specification gap: email case sensitivity"
git push
```

## Done when

- [ ] You have fixed a code bug without touching the specification or its test
- [ ] You have seen what happens when an agent is told "make the test pass", and stopped it
- [ ] You have found a genuine gap by probing the running API through Swagger UI or curl
- [ ] The gap is closed in the order spec → test → code
- [ ] `traceability.md` has a row for the new requirement
- [ ] The suite is green, your commit is in, and it is pushed

## If it goes wrong

**You cannot tell whether it is case A or case B.** Ask one question: *is the specification
describing what the product should do?* If yes, the code is wrong (A). If no, the specification
is wrong (B). It is not about which is easier to change.

**Both curl requests succeeded and you are not sure that is wrong.** It may not be — the point
is that nobody decided. Undefined behaviour is a finding whichever way you then rule.

**You changed the code first and are now backfilling the spec.** Stop and redo it in order. The
sequence is the habit being trained; getting the same end state by a different route does not
build it.
