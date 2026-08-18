# Phase 8 — Do it yourself: signin

## What you'll do

Run the entire workflow again, for a second feature, with no step-by-step instructions.

Everything up to now had a guide. This does not. That is the assessment: not whether you can
follow the sequence, but whether you reach for it unprompted.

## Time

About 2 hours.

## Before you start

Phase 7 complete: signup works, the password minimum is 12 characters, and every artefact
agrees.

## The feature

> A registered user should be able to sign in with their username and password.

That is all you get. Deliberately — it is the same shape of under-specified product idea that
signup started from, and turning it into something buildable is the work.

Both review gates apply, and nobody will remind you: PR 1 for the specification before you plan,
PR 2 for the implementation.

And once signin is finished — specified, built, tested, traced and in a pull request — expect a
change request, exactly as one arrived after signup. Handle it the way you handled that one. You
will get no walkthrough this time.

## First: teach the skill what you learned

Before you start signin, spend fifteen minutes improving
`.claude/skills/django-conventions/SKILL.md`.

You have now watched an agent build a real feature in this project. Some of it went smoothly and
some of it needed correcting — and every correction you had to make is a gap in your instructions.
Recall the signup build:

- What did you have to explain that the skill should have said?
- What did the agent get wrong the first time?
- What convention did you settle on that is written down nowhere?
- What did you catch in review that a rule would have prevented?

Add those. Keep it short — a skill is loaded into context every time it applies, so a bloated one
costs you on every request and dilutes the rules that matter. If it grows past a page, cut the
least valuable line for each one you add.

**This is the measurable part of the exercise.** Signin is a similar feature to signup. If your
skill genuinely improved, signin should need fewer corrections. If it needs just as many, your
skill did not capture what you learned — which is itself worth knowing.

Write down, before you start: *how many corrections did signup need?* Then compare at the end.

## What you do

No commands, no order given. Everything you need you have already used.

Some of what the specification must settle, though you should find more yourself:

- What does a successful signin return?
- What happens on a wrong password?
- What happens for a username that was never registered?
- Should those two cases be distinguishable to the caller? *(Think about this one. There is a
  real security argument, and it is the kind of decision a specification exists to record.)*
- Is signin rate-limited?
- Does anything expire?

## Done when

- [ ] The specification exists, was reviewed, and every requirement can fail
- [ ] The plan and tasks trace to requirements
- [ ] The implementation is generated from them, not hand-written
- [ ] Tests exist and you have broken the code to prove at least one can fail
- [ ] `traceability.md` covers signin as well as signup
- [ ] Both gates were used: PR 1 for the specification, PR 2 for the implementation
- [ ] Any change request that arrived was propagated from the specification outward, not patched
      into the code
- [ ] `pytest` passes
- [ ] You extended `django-conventions` before starting, and it is still under a page
- [ ] You can say whether signin needed fewer corrections than signup, with numbers
- [ ] You hand-wrote no code
- [ ] You can name one ambiguity you found that the tooling did not

That last box is the real one. Everything else can be produced by following the motions.

## When you are done

You have run the full loop twice, changed a requirement, and handled all three kinds of wrong.
The mental model to keep:

```
                 PRODUCT IDEA
                      ↓
                  SPECIFY  ← you decide
                      ↓
                  CLARIFY  ← you decide
                      ↓
                    PLAN
                      ↓
                   TASKS
                      ↓
                 IMPLEMENT
                      ↓
                    TEST
                      ↓
                   VERIFY  ← you decide
                      │
             ┌────────┴────────┐
          Correct          Problem found
             │                 │
           Done        code bug / spec bug / spec gap
                               │
                               ↓
                    update the right artefact
                               │
                               ↓
                            VERIFY
```

Three points on that diagram are marked *you decide*. Those are the ones that do not transfer to
the agent, no matter how good it gets: what the product should do, what the words mean when they
are ambiguous, and whether what came back is genuinely right.

The specification is the source of truth — and it is not immutable. When requirements change or
gaps appear, the specification evolves first, and everything downstream is brought back into
alignment behind it.

## If it goes wrong

**You are stuck on where to start.** Re-read your own phase 2 file. You are allowed to look
back; you are just not being led.

**A change request arrived and you are not sure how far it reaches.** Write down the blast radius
before you touch anything, exactly as you did in phase 7 — which artefacts change, and which
tests. Then compare with what actually changed. The gap between the two is the useful part.

**You are finished and unsure whether it is good enough.** Go to
[phase 9](09-submit-your-work.md) — the self-audit there is designed to answer exactly that,
and it will find things you did not notice.

**Your specification came out much shorter than the signup one.** Probably right — signin is a
smaller feature. But check the failure cases specifically. That is where signin hides its
complexity, and it is where the interesting security decision lives.
