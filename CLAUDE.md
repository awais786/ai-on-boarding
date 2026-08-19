# Working on this repository

## What this is

A **course**, not an application. There is nothing here to run or deploy. The artefacts are
markdown files plus one pytest suite that is never executed against this repo — it runs against a
*learner's* project.

Do not try to build, fix or lint a Django project here. There isn't one. Learners generate their
own from `facilitator/scaffold-spec.md`.

## The wall between `exercise/` and `facilitator/`

**This is the rule most easily broken by a well-meaning edit.**

Learner content lives on `main`. Facilitator content lives on the **`facilitator` branch**, which
carries everything — the exercise plus `facilitator/` — so whoever runs the course sees both.

**Sharing rule: learners work from `main`. Never merge `facilitator` into it.**

A branch is not access control; anyone who can clone can `git branch -a`. It keeps the answers out
of the working tree learners read, which is the practical protection this course needs.

**This file lives only on `facilitator`.** It describes the withheld material, so it is not part
of what learners get.

**Keeping them in sync:** make learner-facing changes on `main`, then merge `main` into
`facilitator`. Never the other way. A merge in the wrong direction publishes the answers, and it
is the one mistake that cannot be quietly undone once devs have pulled.

**Never fast-forward this branch.** `main` deleted `facilitator/` and `CLAUDE.md` in the commit
that created the split, so a fast-forward merge does not merge anything — it moves this branch to
`main`'s tip and the withheld material disappears. That is exactly how it was lost once already.

Sync like this, and check before pushing:

```bash
git checkout facilitator
git merge --no-ff main
ls facilitator/ CLAUDE.md      # both must still exist
git push
```

If either is missing, do not push. Recover with `git checkout <last-good-commit> -- facilitator`.

Several things are withheld from learners **on purpose**, because finding them is the skill being
trained:

| Withheld | Where it lives | Why |
|---|---|---|
| Everything in `facilitator/` | `facilitator/` | See below |
| The mid-course events | `facilitator/change-requests.md` | Scheduled surprises are not surprises |
| The conformance suite | `facilitator/conformance/` | A learner who sees it builds to it instead of to their own spec |
| The traps, timings and assessment strategy | `facilitator/GUIDE.md` | It also spoils the phase 7 payoff |

The clarification checklist is the exception that proves the rule: learners *do* need it, at phase
3 step 3, so it lives in `reference/` rather than the guide. Timing is controlled by the
instruction, not by hiding the file.

**Never move any of this into `exercise/`, and never summarise it there.** Adding "here are the
ambiguities to look for" to phase 3 feels helpful and destroys the exercise. If a learner-facing
file needs to reference withheld material, it points at *when* to open it, never at what it says.

## The shape of a phase file

Every `exercise/*.md` has these six sections, in this order. New phases match it:

1. `## What you'll do`
2. `## Time`
3. `## Before you start` — the previous phase's exit criteria
4. `## Steps` — numbered, second person, exact commands
5. `## Done when` — a checkbox list a learner can verify alone
6. `## If it goes wrong` — real failures, with the fix

Learner files are second person and tell them what to do. Facilitator files are third person and
tell the facilitator what to watch for.

## Invariants — do not drift these

These are decisions, not defaults. Each has been deliberately set, and at least one has been
reverted once already.

- **Tests come AFTER implementation.** This is not TDD. Do not add tests-first language, red-green
  framing, or "write the failing test" steps anywhere. The compensating control is that learners
  break working code to prove a test can fail.
- **No hand-written code.** Learners edit instructions — specification, constitution, skill — and
  agents produce code. Stated in `README.md`, encoded as a constitution principle in phase 2, and
  checked in phases 4, 8 and 9. If you change it in one place, change all four.
- **Django is never a prerequisite.** The audience is fresh devs. Prerequisites are Python, git, a
  terminal, a GitHub account, Claude Code. Django is the material, never the subject.
- **Conformance assertions stay class-based.** `4xx` for rejections, `2xx` for successes — never an
  exact status code, never a specific password minimum. Every learner's specification differs
  legitimately; tightening an assertion makes the suite fail correct work.
- **Two review gates, not three.** PR 1 on the specification after phase 3, PR 2 on the
  implementation after phase 5. Reviews are non-blocking — learners keep building while the lead
  reads, and feedback is folded in as a specification change. Do not add a third gate; the
  waiting cost was weighed and rejected.
- **Change requests arrive unscheduled, from the lead, and always onto a FINISHED feature** —
  never mid-build. A complete baseline is what makes the blast radius measurable. Learner-facing
  files say only that requests may arrive and what to do; never name the request, never say when
  it comes.
- **Reviews terminate.** `facilitator/review-contract.md` governs every review: only findings
  citing a requirement identifier, a named failing test or a documented convention may block; the
  finding list closes after round one; two rounds is the cap. Do not add review guidance anywhere
  that contradicts it, and do not soften the cap.
- **Requirement identifiers are permanent.** Specs number requirements `R1`, `R2`, …; new ones
  append, changed ones keep their number, removed ones leave a gap. The traceability table, the
  PR template and the review prompt all key off them.
- **`django-conventions/SKILL.md` stays under a page.** Skills load into context whenever they
  apply, so a bloated skill costs on every request and dilutes the rules that matter.

## What moves together

Most breakage here is a change made in one file and not its partners.

| Change | Also update |
|---|---|
| A phase's time estimate | The `README.md` table, the stated total, `facilitator/GUIDE.md` timing |
| A phase's filename | The `README.md` link, and any cross-reference in other phases |
| Adding or removing a phase | `README.md` table, `facilitator/GUIDE.md` sticking points and teaching table |
| A step's number inside a phase | Later steps in that file, and any "phase N step M" reference elsewhere |
| The scaffold spec | Phase 1's acceptance checks and its `Done when` list |
| A conformance check | `facilitator/conformance/README.md`'s table of what is checked and why |
| A review rule | `review-contract.md`, `lead-review-checklist.md`, `review-prompt.md`, and phase 3 step 8 |
| A change request | `facilitator/change-requests.md`, and the phase that expects it (7 or 8) |
| A learner-facing asset | Keep it in `starter/` or `reference/` — never `facilitator/` |
| A field on signup or signin | The conformance suite, the clarify checklist in `GUIDE.md`, phase 2's seed requirement |

The `README.md` phase table must sum to the stated total. It has been wrong before.

## Volatile facts

Command names, package versions, tool behaviour and file conventions move. Anything of that kind:

- Source it at edit time from official documentation — **never from memory**
- State the verification date in the file that carries the fact
- Prefer a short list that is right over a complete one that is stale

Highest-churn items: Spec Kit's `/speckit.*` command names, whether Claude Code reads `AGENTS.md`,
and the Django version pinned in the scaffold spec.

## Deliberately out of scope

Do not add these back without being asked: GitHub Issues integration, Spec Kit's `analyze` and
`checklist` commands, tools other than Claude Code, Postman as a required dependency, TDD.

## Verifying the repo is still sound

After any structural edit:

```bash
# 1. No dead internal links (skips this file, whose code blocks contain the pattern itself)
for f in $(find . -name '*.md' -not -name 'CLAUDE.md'); do d=$(dirname "$f"); \
  grep -o '](\.\./[^)]*\|](exercise/[^)]*\|](facilitator/[^)]*\|](glossary\.md\|](0[0-9][^)]*' "$f" \
  | sed 's/^](//' | while read -r l; do [ -e "$d/$l" ] || echo "DEAD $f -> $l"; done; done

# 2. Phase titles match filenames
for f in exercise/*.md; do printf "%-40s %s\n" "$(basename $f)" "$(head -1 $f)"; done

# 3. Conformance suite still compiles
python3 -m py_compile facilitator/conformance/*.py

# 4. No answer leakage into learner-facing files
grep -rn "answer key\|ANSWER-KEY\|conformance" exercise/ || echo "clean"
```

Check 4 should return only references that tell a learner *when* to open something — never
content from it.
