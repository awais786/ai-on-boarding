# Review contract

Rules for every review in this course — the lead's, and any agent's. Their purpose is to make
review **terminate**.

## Why review does not terminate by default

Asked *"is this good?"*, a reviewer will always find something, because any code can be improved
indefinitely and reporting nothing feels like failing the task. Each round invents a fresh
standard, re-discovers problems that were already there, and re-raises items that were settled
three rounds ago. Ten rounds later the author has stopped reading.

This contract replaces *"is this good?"* with *"does this meet the specification?"* — a question
with an answer, and therefore an end.

---

## Rule 1 — Review the change, not the codebase

The reviewable unit is what this pull request changes.

Pre-existing problems in untouched code are recorded in a backlog and **never block**. Recording
them is useful; blocking on them means nothing can ever merge, because every codebase has a
backlog.

## Rule 2 — Only traceable findings block

A finding may block **only** if it cites one of:

1. **A requirement identifier** — "`FR-004` says tokens expire in 30 minutes; this one does not."
2. **A named failing test.**
3. **A documented convention** from the constitution or `django-conventions`.

Everything else is a **nit**: recorded once, never blocking, never re-raised.

*"I would have written this differently"* is a nit. *"This is not idiomatic"* is a nit unless it
names the convention it violates. *"Consider extracting a helper"* is a nit. These are not
worthless — they are simply not grounds to withhold a pass, and treating them as grounds is what
makes review endless.

If you cannot point at a requirement, a test, or a convention, you do not have a blocker. You
have a preference.

**One labelled exception.** A security or data-loss defect blocks even when the specification is
silent, provided you describe a concrete failure path. This is an exception, not a fourth kind of
traceability, and it is the clause a reviewer will be tempted to stretch. "This feels insecure"
does not invoke it. If it is being used more than rarely, the specification is what needs fixing.

## Rule 3 — A clean verdict is a legitimate outcome

A review that finds no blockers is a **successful review**, not a lazy one. Say so plainly to any
agent you ask to review, because a reviewer that treats zero findings as failure will invent some.

The review's final line is exactly one of:

```
Gate 1   APPROVED                     |  CHANGES REQUESTED (n)
Gate 2   PASS                         |  BLOCKED (n)
```

There is no third verdict. "Mostly fine, but…" is not a verdict. A verdict may be accompanied by
any number of nits.

**At gate 2, a passing test suite is a precondition for PASS**, not a finding. A change whose
tests fail cannot pass regardless of how few issues were found.

## Rule 4 — Findings freeze after round one

**This is the rule that makes the process terminate. The others leak without it.**

- **Round one** produces the complete list. Everything you intend to raise, you raise now.
- **Round two** verifies only that those findings were addressed, plus any regression the fixes
  introduced. It does not go looking for new material.

A second pass that goes hunting will always find something, and a third will find something else.
The list is closed after round one.

## Rule 5 — Two fix rounds maximum

If it is still blocked after the second round, **stop reviewing**.

A third round means reviewer and author are working from different standards, and more review
will not reconcile them — it will generate a fourth round. The disagreement is upstream, in the
specification.

Escalate: fix the specification, then re-review against the corrected specification as a fresh
round one. This is the **spec bug** case from phase 6, arriving in real life.

Capping rounds looks like abandoning quality. It is the opposite. Unbounded review does not
produce quality; it produces churn, and eventually the author ignores the reviewer entirely —
which is where quality actually goes to die.

## Rule 6 — A ledger carries state across rounds

Every finding is recorded with the status it has **at the moment of discovery**, so a fresh
session cannot re-litigate what was settled.

```markdown
## Review: Implement signup — round 1 — 2026-08-19

| # | Severity | Finding | Cites | Status |
|---|---|---|---|---|
| 1 | BLOCKER | Reset token has no expiry | FR-007 | open |
| 2 | BLOCKER | No test for the unknown-email path | FR-005 | open |
| 3 | NIT | `_build_url` could take a named arg | — | accepted as-is |

BLOCKED (2)
```

Statuses are exactly `open`, `fixed`, `accepted as-is`, `deferred`. Only `open` survives a round.
An accepted or deferred finding is closed and is not raised again on the same change.

## Rule 7 — Disagreement resolves against the specification

Not by seniority, not by who is more insistent, not by who replies last.

If the specification is silent on the point, then by Rule 2 the finding is a nit — **and the
silence is itself logged as a spec gap**, so the next specification is better than this one.

---

## What a reviewer must not do

| Anti-pattern | Why it breaks termination |
|---|---|
| Reviewing whole files because the diff touched them | Re-discovers the backlog every round |
| Raising a nit as a blocker "to be safe" | Nothing ever passes; the severities stop meaning anything |
| Finding new issues in round two | The list was closed; this restarts the loop |
| Re-raising an `accepted as-is` finding | The ledger exists precisely to prevent this |
| Ending with suggestions instead of a verdict | An unresolved review is an open loop by construction |
| Softening a real blocker to avoid seeming harsh | Ships the defect and wastes the review |
| Padding a clean review with invented findings | The single most common cause of endless review |

## The procedure

```
1. Establish scope     → the change, and the requirements it claims to satisfy
2. Round one           → find everything; classify BLOCKER or NIT by Rule 2
3. Write the ledger    → every finding, with its citation
4. Emit a verdict      → APPROVED / PASS, or CHANGES REQUESTED / BLOCKED (n)
5. If blocked          → the author fixes blockers only
6. Round two           → verify those fixes and their regressions ONLY
7. Emit a verdict
8. If still blocked    → stop. Fix the specification, not the code. Restart at 1.
```
