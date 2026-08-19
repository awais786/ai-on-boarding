# Lead review checklist

For whoever reviews a learner's pull requests. Two gates, and they ask different questions —
reviewing gate 1 as though it were code is the most common way to waste it.

**Read [`review-contract.md`](review-contract.md) first.** It is not optional background: it
defines what may block, when the finding list closes, and when to stop reviewing. Without it,
review of a learner's work runs forever, which is the single most common complaint about
AI-assisted review and the thing this course must not reproduce.

The three rules you will be tempted to break:

- **Only a finding citing a requirement identifier, a named failing test, or a documented
  convention may block.** Everything else is a nit — record it, do not withhold approval for it.
- **Your finding list closes after round one.** Round two verifies those findings and nothing else.
- **Two rounds, then stop.** Still blocked means the specification is wrong, not the code.

## Turnaround

Learners are told to keep working while they wait, so you are not blocking them. But feedback
that arrives after they have finished the whole feature teaches nothing about specification
review, so aim for **same working day**.

---

## Gate 1 — the specification

Opened at the end of phase 3. Contains the constitution, the specification, the clarifications,
and the learner's own `review-notes.md`.

**There is no code yet. Do not ask for any.**

The single question: *could two competent developers read this and build different things?*

- [ ] Every requirement carries an identifier (`R1`, `R2`, …). Without them the traceability
      table has nothing stable to point at, and the PR template's requirements table cannot be
      filled in honestly.
- [ ] Every requirement names something that can **fail**. "Passwords should be secure" is not a
      requirement; "at least 8 characters, rejected with 400 and a field-level error" is.
- [ ] No requirement can be read two ways.
- [ ] The edge cases are decided: duplicate email, duplicate username, invalid email, short
      password, and what a success returns.
- [ ] **Username and email are both settled** — uniqueness, case sensitivity, and what happens if
      one user's username matches another's email address.
- [ ] The password is explicitly never returned in any response.
- [ ] No implementation detail has leaked in. No Django class names, no ORM constructs, no
      module paths.
- [ ] Requirements do not contradict each other.
- [ ] The constitution is about standards, not about this feature.

**Your verdict, as the last line of your review:**

```
APPROVED                 or    CHANGES REQUESTED (n)
```

`APPROVED` with nits attached is a perfectly good outcome, and the common one on a second
attempt. Approving a specification you have nits about is not lowering the bar — a nit by
definition is something no requirement, test or convention supports.

**What to push back on.** Vagueness, not style. If you find yourself commenting on wording
preferences, stop — the question is whether a test could be written from it, not whether you
would have phrased it that way.

**A useful move:** pick one requirement and describe an implementation that technically complies
but is obviously wrong. If you can find one, the requirement is too loose. Say so and let them
fix it.

---

## Gate 2 — the implementation

Opened at the end of phase 5. Contains plan, tasks, code, tests and the traceability table, with
the plan in the PR description.

The question shifts: *does this do what the approved specification said?*

- [ ] The PR description carries a plan a reader can judge without opening the diff.
- [ ] Every requirement in the specification has a row in `traceability.md`, **matched by
      identifier** — not by prose that looks similar.
- [ ] No identifier was renumbered since gate 1. Compare against the specification you approved;
      silent renumbering breaks every reference made before it.
- [ ] No requirement has an empty Test column.
- [ ] The tests assert **behaviour**, not just status codes. A requirement about what is stored
      needs an assertion about what is stored.
- [ ] They can tell you which requirements they broke to prove the tests could fail, and what
      they changed.
- [ ] No behaviour exists in the code that no requirement asked for.
- [ ] The OpenAPI schema agrees with the specification — especially that no response schema
      exposes a password.
- [ ] No code was hand-written. Ask if you are unsure; a surgical edit inconsistent with the
      surrounding style is the tell.
- [ ] Any change request that arrived is folded in, and the **specification** was updated, not
      just the code.
- [ ] The pull request references the change-request issue, and the issue is still open — they are
      told to close it on merge, not before.
- [ ] The requirements the request produced are in the specification, not only in the issue. A
      requirement living in a GitHub comment is one nobody finds later.

**Your verdict, as the last line of your review:**

```
PASS                     or    BLOCKED (n)
```

A passing test suite is a **precondition** for PASS, not a finding. If the suite is red, the
verdict is BLOCKED regardless of how little else you found.

**The highest-value question at this gate:** *"which test would fail if this requirement were
violated?"* Ask it about two or three requirements. If they cannot answer immediately, the
traceability table was filled in as paperwork rather than by looking.

---

## What both gates share

Learners have been taught that a change to the specification propagates: spec → plan → tasks →
tests → code → traceability. Your feedback is a change to the specification.

So when you request a change at either gate, expect it to come back with **more than the code
edited**. If a learner responds to spec feedback by changing only the implementation, that is the
finding worth raising — it is the exact failure the whole course is built to prevent.

And both gates end the same way: a verdict on the last line, a ledger of findings with their
status, and at most two rounds. If you reach a third, the specification is what needs fixing —
send it back to gate 1 rather than continuing to review code.
