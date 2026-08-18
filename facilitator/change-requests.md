# Change requests

Two requests arrive during the exercise. **Learners must not see this file.** Their materials say
only that requests may arrive mid-build and what to do when one does — never what, and never when.

The point is that a real change request is unscheduled. A learner who knows a "surprise" is coming
on page 12 is not practising anything.

---

## CR-1 — Terms of service (during signup)

**Send when:** signup is **finished** — phase 5 complete, tests green, traceability filled in,
PR 2 open. Send it as they begin phase 7, after they have done the password-minimum change.

Not mid-build. A change request landing on a half-built feature muddles the lesson, because half
the artefacts do not exist yet and the blast radius cannot be measured. Landing it on a complete,
verified feature is both cleaner to teach and how change requests actually arrive.

**Send verbatim:**

> Product has come back on signup. Before we launch we need users to accept the terms of service
> when they create an account — legal will not sign off otherwise. Can you get this into the
> current work rather than a follow-up?

That is all. Do not specify a field name, a type, or a status code. Do not say what "accept"
means. The gaps are the exercise.

**What you are watching for:**

The request hides a decision most people miss: do you store *that* the user accepted, or *when*
and *which version* of the terms? "Legal will not sign off" is a hint that a boolean is probably
not enough — a compliance question a specification must settle and code cannot.

- [ ] They updated the **specification first**, not the code
- [ ] They asked what "accept" means rather than assuming a boolean
- [ ] They noticed the version/timestamp question, or can be led to it with one nudge
- [ ] The PR description was amended — a PR still describing the old feature is the common miss
- [ ] The new requirement took the **next free identifier** — nothing was renumbered
- [ ] Plan, tasks, tests, traceability and the OpenAPI schema all moved
- [ ] They considered whether this belongs in signup at all, and said why either way

**If they only change the code and tests:** that is the finding. Ask them what the specification
now says, and let them notice it describes software that no longer exists.

---

## CR-2 — Sign in with email as well as username (during signin)

**Send when:** signin is **finished** — specified, implemented, tested, traced, and in PR 2.
Same principle as CR-1: a complete baseline, then the change.

This is the assessment. No guidance accompanies it, and phase 8 tells them only that a request
may arrive and to handle it as they did before.

**Send verbatim:**

> Support is getting tickets from users who cannot log in — they are typing their email address
> because that is what they remember. Can we let people sign in with either their username or
> their email?

**What you are watching for.** This is the richest request in the exercise. Four things it
surfaces, in rough order of how often they are missed:

1. **Backwards compatibility.** Existing clients send `username`. Does that still work? Almost
   nobody raises this unprompted, and it is the question that dominates real feature work.
2. **Identifier collision.** What if one user's username is another user's email address? There
   is no obviously correct answer — which makes it a specification decision, not a lookup detail.
3. **Error-message security.** "No such username" leaks which accounts exist; "invalid
   credentials" does not. They met account enumeration in phase 6 — do they connect it here
   without being told?
4. **The request contract changed meaning.** The field is no longer a username; it is an
   identifier that may be either. The schema and its documentation both have to move.

- [ ] Specification updated before any code
- [ ] Backwards compatibility explicitly decided, either way
- [ ] The collision case is addressed rather than left to whatever the ORM happens to do
- [ ] Error messages do not reveal which accounts exist
- [ ] Tests cover signing in by both identifiers, plus the collision case
- [ ] New requirements took the next free identifiers; nothing was renumbered
- [ ] Traceability, schema and PR description all updated

**Do not hint.** If they miss backwards compatibility entirely, let them, and raise it at gate 2.
Watching a learner realise at review that they broke every existing client is worth more than a
prompt that prevents it.

---

## Running both

CR-1 is guided — phase 7 part two walks them through the propagation, right after they have done
the smaller password-minimum change by hand. The escalation is deliberate: a value change first,
then one that makes the specification grow.

CR-2 is not guided. Phase 8 is where the scaffolding comes off, and the question is whether they
reach for the discipline unprompted.

If a learner handles CR-1 well and CR-2 badly, that is the most useful signal the exercise
produces: they can follow the motion, but have not yet internalised it.
