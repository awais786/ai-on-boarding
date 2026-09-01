## Context

See proposal.md - Why.

Two entry points complete a reset today: the JSON completion endpoint, and the page served at
the delivered link. Both call one shared completion routine, so that *Retire a reset code once it
is used* and *Invalidate existing authentication tokens on reset* cannot hold for one and quietly
fail for the other.

The page already runs its checks in a deliberate order: it decides whether the link is usable
before it looks at the password, so that a dead link cannot render a live form just because the
password was also bad. That ordering is load-bearing for *An unusable link says so and offers no
form*, and this change has to slot into it rather than in front of it.

Nothing about a password is persisted anywhere. The stored reset record holds a digest of the
code, when it was issued, and whether it is still usable - never a password.

## Goals / Non-Goals

**Goals:**

- A person choosing a password they cannot see gets one chance to catch a typo before it is
  committed.
- The added field changes nothing about how codes are issued, delivered, expired, superseded, or
  retired, and nothing about the responses that keep the reset path from revealing which
  addresses have accounts.

**Non-Goals:**

- Password confirmation anywhere else - signup is untouched.
- Any change to the shared completion routine. If this change needs to modify it, the design is
  wrong.
- Live, in-browser feedback as the person types. The comparison happens on submission.

## Decisions

### The comparison lives in the page, not in the shared completion path

*Complete a reset through the API with a single password* says the JSON endpoint keeps taking one
password, and *Require the two password entries to match* binds only the page. Putting the
comparison in the page's own submission handling satisfies both without a flag or a mode.

**Alternative considered - put it in the shared completion routine and make the second entry
optional there.** Rejected: it makes the routine's behaviour depend on which caller it came from,
which is exactly the property the shared routine exists to avoid. The routine is shared because
security invariants must not diverge between entry points; teaching it that one entry point has
different input rules undermines the reason it is shared at all.

**Alternative considered - require confirmation on the API as well.** Rejected on the reasoning
recorded in proposal.md - the asymmetry is deliberate and is written down as a requirement so it
reads as a decision rather than an omission.

### Order: link state, then match, then strength

*Decide the link before the password* keeps the existing link check first. *Report a mismatch
before judging the password* puts the comparison ahead of the strength check.

Each step is a refusal that renders and returns, so the order in the code is the order in the
spec, and no step can observe a value a previous step has already rejected.

**Alternative considered - report every problem found.** Rejected by *A mismatch is reported ahead
of a strength complaint*: telling someone their password is too weak, when the password they
meant to type may be perfectly strong, is feedback about a string they did not intend to submit.
It also invites them to "fix" the wrong thing.

### The confirmation is a form input and nothing else

*Never retain the confirmation entry* is satisfied by construction: the second entry is read from
the submission, compared, and never handed to anything that stores. No model field, no migration,
no column. Worth stating explicitly because "should not be in the database" is the kind of
property that is trivially true when written and quietly false three changes later.

Neither entry is echoed back into the re-rendered form. A refused submission returns an empty
form and the reason it was refused. This is what *The confirmation is absent from every response*
requires, and it is also why a mismatch has to leave the link usable - the person has nothing to
correct in place and must retype both entries.

### A mismatch never reaches the code-spending step

*A mismatch does not spend the reset link* falls out of returning before the completion routine is
called: the routine is the only thing that retires a code. The requirement is stated anyway
because it is the property most likely to break silently if the order is ever rearranged.

## Risks / Trade-offs

- **An empty second entry could be read as "no confirmation supplied" and waved through, rather
  than as a mismatch.** → *A second entry left empty is a mismatch* pins it as a scenario, so the
  empty case is tested rather than inferred.

- **A later change adds confirmation to the JSON endpoint "for consistency", quietly breaking
  every existing API caller.** → *Complete a reset through the API with a single password* makes
  the single-password form a requirement with a test behind it, so the change fails rather than
  merges.

- **A later change reorders the checks so strength is judged first, or reports both problems at
  once.** → Both orderings are pinned by scenarios rather than left to code comments.

- **Existing tests that submit the reset form will fail until they send the second entry.** →
  Expected and mechanical. The failures are the signal that the form's contract changed; each one
  is a submission that needs the second field added.

- **Two round trips for a submission that is both mistyped and weak.** → Accepted, and the direct
  consequence of reporting the mismatch first. A person who mistyped cannot act on a verdict about
  the password they did not mean to enter.
