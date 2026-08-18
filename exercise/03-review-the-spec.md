# Phase 3 — Review the specification

## What you'll do

Read your specification as a critic and find what is still ambiguous, untestable, or missing —
**before** any code exists.

This is the first major human checkpoint. AI can draft and refine a specification. It cannot
decide what your product should do. That decision is yours, and this is where you make it.

## Time

About 45 minutes.

## Before you start

Phase 2 complete: a constitution, a signup specification, and clarification answered.

## Steps

### 1. Learn what a testable requirement looks like

One worked example. Here is a requirement as specifications usually arrive:

> Passwords should be secure.

It is useless, and the reason is precise: **nothing here can fail.** No test can be written
against it, two developers will build different things, and both will believe they complied.

The same requirement, made testable:

> A password must be at least 8 characters. A signup request with a shorter password is rejected
> with HTTP 400 and a field-level error identifying `password`. Passwords are stored using
> Django's default password hasher and are never included in any API response.

Four things changed. It names a **threshold** (8), a **response** (400 with a field error), a
**storage rule** (default hasher), and a **prohibition** (never returned). Every one of those can
be turned into a test that fails when the code is wrong.

That is the standard. Apply it to your own specification now.

### 2. Find the ambiguities yourself — before reading any list

Open your specification and write down every question it leaves unanswered. Do this in a file,
`review-notes.md`, so you can compare later.

Work through it slowly. Aim for at least eight. Prompts if you stall — what happens at the
boundaries, what happens twice, what comes back on success, what is never allowed out.

**Do not ask Claude for the list, and do not open the checklist yet.** Finding ambiguity is the
skill being trained. Reading someone else's list is not practice.

### 3. Now compare

Open [`reference/clarification-checklist.md`](../reference/clarification-checklist.md) and read it.

Count what you found and what you missed. Missing several is completely normal on a first
attempt — the number matters far less than noticing the *kind* of thing you overlooked. Most
people miss the same category twice, and knowing your own blind spot is the point.

### 4. Interrogate the specification

For each requirement, ask the six review questions:

- Can it be understood only one way?
- Can it be tested?
- Are the edge cases defined?
- Does it conflict with another requirement?
- Is it implementation-specific when it should not be?
- Does it match what the product should actually do?

Fix what fails, in the specification. Ask Claude to make the edits, then read them.

### 5. Give every requirement an identifier

Number them. `R1`, `R2`, `R3`, straight through the specification.

This looks like bureaucracy for about ten minutes, and then it is the thing everything else hangs
off. Your traceability table will have a row per identifier. Your pull requests will list the
identifiers they satisfy. When someone asks *"which test covers R4?"* there is exactly one answer,
and finding it takes seconds rather than re-reading a document.

**One rule, and it matters more than the numbering itself: identifiers are permanent.**

When a requirement is added later — and one will be — it takes the next free number. When a
requirement changes, it keeps its number. When a requirement is removed, its number is retired,
never reused.

Renumbering feels tidy and is quietly destructive: every traceability row, every pull request,
every review comment that mentioned `R4` now points at something else, and nothing warns you.
A gap in the sequence is not untidiness. It is history.

### 6. Approve it, deliberately

Say out loud, or write at the top of the file: *this describes what signup must do, and I am
accountable for it.*

That sounds theatrical. It is doing real work: from here on, the code is judged against this
document. If the document is wrong, the code will be faithfully, confidently wrong.

### 7. Open PR 1 — the specification

Your lead reviews the specification **before** any plan or code exists. This is the highest-value
review in the whole process: changing your mind here costs a paragraph, and changing it after
implementation costs a day.

```bash
git checkout -b feature/signup
git add .
git commit -m "Add constitution and signup specification"
git push -u origin feature/signup
```

Open a pull request titled **`Specification: signup`**. The template will prompt you — fill in
every section. For a specification PR, *Requirements it satisfies* lists the requirements this
establishes, and *How to verify it* is how a reader checks the spec is complete, not how to run
code.

Fill in **What I am unsure about** honestly. Name the decision you made most arbitrarily. That
section is what turns a review into a conversation instead of a rubber stamp.

### 8. Know the rules you are reviewed under

Your lead reviews to a contract, and it is worth knowing before your first review lands.

**Only certain findings can block you.** A comment blocks approval only if it cites a requirement
identifier, a named failing test, or a documented convention from your constitution or your
skill. Anything else is a **nit** — recorded, but not a reason to withhold approval. *"I'd have
done this differently"* is a nit.

**The finding list closes after the first round.** Round two checks that you fixed what was
raised, plus anything your fixes broke. Your reviewer does not go hunting for new material.

**Two rounds, then stop.** If it is still blocked after two, the problem is not your code — it is
the specification, and it goes back to be re-specified rather than reviewed a third time.

This matters to you for one practical reason: **a review that never ends is a broken review, not
a thorough one.** If you find yourself on round four, say so and ask which requirement the
outstanding finding cites. If there isn't one, it is a nit.

You will also be on the other side of this eventually. The same rules apply when you review
someone else — including the hardest one, which is that finding nothing is a legitimate outcome
and you should not invent something to look diligent.

### 9. Keep going — do not wait

Your lead will take a while. **Carry on to phase 4 on the same branch.**

When feedback arrives, it is a change to the specification, and you already know what that
means: the specification changes first, then everything downstream follows. You will meet this
formally in phase 7. Meeting it for real first is better.

## Done when

- [ ] `review-notes.md` contains your own list, written before you opened the guide
- [ ] You have compared it against the facilitator checklist and noted what you missed
- [ ] Every requirement has an identifier — `R1`, `R2`, … — and you know they are permanent
- [ ] Every requirement in the specification names something that can fail
- [ ] No requirement can be read two ways
- [ ] Duplicate emails, duplicate usernames, invalid emails, short passwords, and the success
      response are all defined
- [ ] You have decided what happens if one user's username matches another user's email address
- [ ] PR 1 is open, titled `Specification: signup`, with every template section filled in
- [ ] *What I am unsure about* names something real
- [ ] You know what can and cannot block your PR, and that the finding list closes after round one

## If it goes wrong

**Everything looks fine to you.** It usually is not — try the inversion: for each requirement,
ask *"how would I build something that technically complies but is obviously wrong?"* If you can
find such an implementation, the requirement is too loose.

**You cannot tell whether something is spec or plan.** Ask: would a caller of the API notice?
If yes, it belongs in the specification. If it is only visible to someone reading the source,
it belongs in the plan.

**Claude renumbered your requirements while editing.** Put them back. Say: *"Requirement
identifiers are permanent. Never renumber them — new requirements take the next free number, and
removed ones leave a gap."* Then add it to your project skill so it does not happen again.

**Claude keeps re-adding implementation detail when it edits.** Tell it once, firmly: *"This
document describes observable behaviour only. Do not name Django classes, modules or ORM
constructs in it."*
