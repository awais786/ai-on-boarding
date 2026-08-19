# Review prompt — code against *their* specification

The conformance suite checks what is true for everyone. This checks the thing that actually
matters and cannot be automated: **did this learner build what their own specification says?**

## How to run it

In a **fresh** Claude Code session, inside the learner's repository. Fresh matters — a session
that helped write the code is biased toward approving it, and will defend choices it made.

Paste the prompt below. It takes a few minutes and produces a report you can read alongside the
conformance results.

---

```
You are reviewing a learner's implementation of a signup feature against the specification
they wrote for it. You did not write any of this code and have no stake in it.

Read, in this order:
1. Their specification (under .specify/ or specs/ — find it)
2. Their technical plan and task list
3. traceability.md, if present
4. The implementation and its tests

Then answer these five questions, and only these. Cite file:line for every claim.

1. REQUIREMENT COVERAGE
   List every requirement in their specification by its identifier (FR-001, FR-002, ...). For
   each, state whether it is implemented, and where. A requirement with no
   implementation is the finding that matters most — say so plainly.

   Then check identifier integrity: does every identifier in traceability.md exist in
   the specification, and does every requirement in the specification appear in
   traceability.md? Report any identifier that appears in one and not the other, and
   any sign that requirements were renumbered rather than appended — for example a
   change request's new requirement occupying a low number.

2. TEST COVERAGE
   For each requirement, name the test that verifies it. Then judge whether that test
   would actually FAIL if the requirement were violated. A test asserting only a status
   code, where the requirement is about behaviour, does not verify the requirement —
   report it as unverified even though it passes.

3. UNSPECIFIED BEHAVIOUR
   Find behaviour in the code that no requirement asked for. For each, say whether it is
   an undocumented requirement they should write down, or scope creep they should remove.

4. SPECIFICATION QUALITY
   Name any requirement that cannot be tested as written, or that could be read two ways.
   Quote it, and give a rewritten version that could fail.

5. TESTS THAT ONLY DESCRIBE THE CODE
   Tests here are written after the implementation, so some will have been shaped by it
   rather than by the specification. Find them. Look for tests that assert only a status
   code where the requirement is about behaviour, tests that assert a value copied from
   the implementation rather than stated in the specification, and any test whose
   assertion would still hold if the requirement were violated. Name each one and say
   what it would need to assert instead.

6. INSTRUCTION COVERAGE
   Read .claude/skills/django-conventions/SKILL.md. Find conventions the code follows
   that the skill does not state, and rules the skill states that the code breaks.
   Then check the git history for changes that look hand-written rather than generated —
   small surgical edits to generated files, inconsistent with the surrounding style.
   Report any you find, and say which instruction artefact should have produced that
   change instead.

7. DRIFT
   Compare the OpenAPI schema at /api/schema/ against their specification. Report any
   disagreement — a status code, a field, a response shape. Pay particular attention to
   whether any password field appears in a response schema.

Classify every finding as BLOCKER or NIT before reporting it. A finding may be a
BLOCKER only if it cites a requirement identifier, a named failing test, or a
documented convention from the constitution or the project skill. Everything else is a
NIT: report it once, and do not treat it as grounds for a negative verdict.

A review that finds no blockers is a successful review. Do not manufacture findings to
appear thorough.

Do NOT fix anything. Do NOT edit any file. Produce the report only.

End with exactly one of these as the final line:

    PASS
    BLOCKED (n)

where n is the number of BLOCKERs. Nits do not count toward n and never turn a PASS
into a BLOCKED. Precede that line with one summary line: <number> requirements
unimplemented, <number> unverified, <number> unspecified behaviours found.
```

---

## Reading the report

This prompt follows [`review-contract.md`](review-contract.md): only findings citing a
requirement, a test or a convention can block, and the finding list closes after the first round.
If you re-run it after fixes, ask it to verify the previous findings rather than review afresh —
otherwise it will find new material indefinitely, which is the behaviour the contract exists to
stop.

The verdict line is a summary, not a grade. What tells you whether the learner understood the
exercise is *which* category their problems fall into.

**Unimplemented requirements** — usually means they never verified, only ran tests. Send them
back to phase 5 and the traceability table.

**Unverified requirements** (a test exists but cannot fail) — the most interesting failure, and
the most common. They built the thing and wrote a test that does not protect it. This is exactly
phase 5 step 6, and it is worth walking through with them individually.

**Unspecified behaviour** — the agent added something nobody asked for and the learner accepted
it without noticing. A reading-the-diff problem, from phase 4.

**Untestable requirements** — they did not really do phase 3. The specification was approved
without being interrogated.

**Tests that only describe the code** — the expected failure mode when tests come after the
implementation, and the reason phase 4 asks learners to break the code three times. Everything
downstream is weaker than it looks, because such a test passes whether or not the requirement
holds. Check a couple by hand against the specification.

**Drift between schema and spec** — often a status code. Minor in itself, useful as evidence that
two sources of truth disagree and nobody looked.

Zero across the board on a first attempt is unusual. Treat it with mild suspicion and check
whether the specification is thin — a specification that requires almost nothing is trivially
satisfied, and phase 3 is where that should have been caught.
