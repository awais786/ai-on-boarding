# Agentic Coding Onboarding Course — Design

**Date:** 2026-08-18 (supersedes `2026-08-18-claude-onboarding-course-design.md`)
**Owner:** Awais Qureshi
**Status:** Draft — awaiting review, then implementation plan

---

## Purpose

Take an engineer who has never meaningfully used an agentic coding tool and make them a competent
daily driver of whichever one they use. Competent means six specific things, which are the course's
six disciplines: they can judge output they did not write, they maintain a working agreement with
the agent, they manage context deliberately, they choose models on purpose, they specify before
they build, and they run reviews that terminate.

The course is not a feature tour. Every module is organised around a failure that a new user
reliably hits in their first two weeks, and the exercise is the proof they no longer hit it.

## Audience

Developers with zero or shallow agentic-tool use. They can code. They do not know what a project
instructions file does, why their session forgets things, or that model choice is a decision they own.

### Two tracks, one course

The course has a single body of content. Seniority changes how it is delivered, not what it says —
a content fork would double the maintenance for no teaching benefit.

**Standard track.** Self-paced and solo. Assumes working Django familiarity: the learner can read a
Django view, run migrations and write a test without looking things up.

**Supervised track.** For juniors and recent graduates. Same modules, same exercises, but Modules 3,
5, 6 and 7 are paired with an experienced reviewer, and the Django prerequisite is satisfied by the
pair rather than the individual. Roughly 1.4× the duration.

### The real prerequisite is judgement, not Django

Django familiarity is a proxy. The property the course actually depends on is the ability to
**evaluate code you did not write** — every module after the first compounds on it, and a learner
who cannot tell a correct diff from a plausible wrong one accumulates defects while believing they
are learning.

This is the specific reason agentic tools are riskier for juniors than for seniors: generating code
stopped being the bottleneck, judging it became the bottleneck, and accepting a plausible wrong diff
is now the easiest mistake available. Earlier drafts of this design left that assumption implicit and
excluded juniors to compensate. Module 1 now teaches it directly, which is both a better course for
everyone and the thing that makes the supervised track viable.

Explicitly out of scope: non-engineers and existing power users.

## Vendor neutrality

The six disciplines are properties of working with a coding agent, not of any product. Four of them
— judging output, model selection, spec-driven development and terminating review — are already
tool-independent. Two — the working agreement and context management — are universal in principle
and divergent in mechanics. Only setup is irreducibly per-tool.

### Supported tools

**Tier 1** — full mechanics, walkthroughs and exercises: **Claude Code**, **Cursor**,
**GitHub Copilot** (agent mode).

**Tier 2** — named in the mapping tables, no dedicated setup or walkthrough: **Windsurf**,
**Codex**, **Aider**, **Gemini CLI**.

Tier 1 is deliberately three. Each additional tool multiplies the volatile surface that must be
re-verified every time the course is revised.

### The anti-lowest-common-denominator rule

Vendor-agnostic writing degrades into uselessness by default: "use your tool's context feature"
teaches nothing. The rule for this course:

> Every module states its principle neutrally, then gives a **mechanics by tool** table naming
> a real, concrete mechanic for each Tier 1 tool. If a technique cannot be named concretely for
> a tool, that tool does not claim support for that technique — the table says so.

Worked walkthroughs are shown in **one** tool — Claude Code, as the reference implementation —
because a neutral walkthrough demonstrates nothing. Exercises and verification criteria are
tool-neutral.

### The AGENTS.md situation

Verified 2026-08-18, and the single most useful fact Module 2 teaches:

- `AGENTS.md` is an open standard under the Linux Foundation's Agentic AI Foundation, adopted by
  60,000+ repositories and read natively by Cursor, GitHub Copilot, Codex, Windsurf, Aider,
  Gemini CLI and Zed.
- **Claude Code is the holdout.** Its memory model still reads `CLAUDE.md`; no native
  `AGENTS.md` path had shipped as of August 2026.

Module 2 therefore teaches `AGENTS.md` as the default and treats Claude Code as a named
exception, with the practical bridge (a `CLAUDE.md` that points at `AGENTS.md`) shown explicitly.
This status **must be re-verified at every course revision** — it is the fact most likely to
change.

## Format

Hybrid:

- **Markdown modules are the source of truth.** Readable standalone, publishable, portable.
- **A runner drives the learner through them**, teaching the current module, setting its
  exercise, verifying the result against the learner's working copy, and logging the outcome.

The runner is split so it is not Claude-only:

- `runner-prompt.md` — tool-neutral. States the teaching loop, the verification procedure, the
  logging format, and the hard rules. Any capable agent can be pointed at it.
- `skills/agentic-onboarding/SKILL.md` — a thin Claude Code wrapper over that prompt.
- Cursor and Copilot users reference `runner-prompt.md` directly (rules file or @-mention).

## Scope

Eight modules: setup, judgement, the four named topics, a review module, and a capstone. Skills/extension authoring,
subagents, hooks, MCP and permissions tuning are **out of scope**.

Django is the *vehicle*, not a subject. The course does not teach Django to people who already
know it. It teaches agentic coding practice using a Django codebase, because abstract exercises
produce abstract learning.

## The practice project

Every exercise runs against one project the learner builds across the course: a Django sign-in
application. The course ships a minimal seed; the learner builds the authentication features on
top of it, module by module. This is tool-independent by construction.

### What the seed contains

```
course/agentic-coding/seed/
  manage.py
  requirements.txt
  README.md
  signin/                 project: settings, urls, wsgi
  accounts/               app: minimal models, one or two views, urls
  accounts/tests/         a small, passing test suite
```

The seed is scaffolding, not the lesson. It deliberately does **not** contain sign-up, log-in,
log-out, password reset or two-factor — those are the exercise material.

The seed carries two or three realistic warts (a view doing too much, a code path with no test
coverage), documented in its README as intentional. Modules 1, 3 and 5 need something real to work
on; a spotless skeleton gives them nothing.

### Why a seed rather than the learner's own repository

Everyone starts identical, so exercises are reproducible across tools, verification is reliable,
and the course can ship a reference solution. A learner may run exercises against their own work,
but the written verification criteria assume the seed.

### Security posture

The application uses Django's built-in authentication throughout. The course never has a learner
hand-roll password hashing, session handling or token generation. Where an exercise touches
security-relevant ground — password reset tokens, rate limiting, CSRF — the module states the
framework mechanism to use and why rolling your own is the wrong answer.

## Repository layout

The course has its own repository — `ai-on-boarding` — so the content sits at the root rather than
nested under a `course/` prefix.

```
README.md                      syllabus, tool support matrix, how to start
docs/specs/                    this design, and specs written during the build
modules/
  00-first-session/            per-tool setup: claude-code.md, cursor.md, copilot.md, shared.md
  01-judging-output.md
  02-working-agreement.md
  03-context-management.md
  04-models-and-budgets.md
  05-spec-driven-development.md
  06-review-that-terminates.md
  07-capstone.md
templates/
  review-contract.md           the terminating review contract, adaptable per project
seed/                          the Django sign-in skeleton
judgement-set/                 agent-produced diffs + answer key for Module 1
reference/                     completed solution per module
runner-prompt.md               tool-neutral runner logic
progress-template.md           copied into the learner's working copy at kickoff
skills/agentic-onboarding/
  SKILL.md                     Claude Code wrapper over runner-prompt.md
```

A dedicated repository is what makes the course installable: a learner clones it, works in their
own copy of `seed/`, and never needs the tooling repository it was drafted in.

## Module structure

Every module file has the same eight sections, in this order.

1. **Objective** — one sentence, what they can do afterwards.
2. **The failure this prevents** — the concrete first-two-weeks pain. Motivation before mechanism.
3. **Concepts** — the minimum model needed to do the exercise, stated tool-neutrally.
4. **Mechanics by tool** — a table naming concrete mechanics for each Tier 1 tool, with Tier 2 where known.
5. **Walkthrough** — a worked example in the reference tool, read not run.
6. **Exercise** — done against the practice project, tool-neutral.
7. **Verification criteria** — explicit, written as what a pass looks like. Grades artefacts, never tool transcripts.
8. **Common mistakes** — populated from RED-phase findings, not invented.

## Syllabus

Order is by which failure arrives soonest. The application grows feature by feature.

### Module 0 — First session
Shared: what all agentic tools have in common — the loop, reviewing a diff before accepting it,
permission and approval models, when to stop the agent. Then a per-tool setup file: install,
authentication, opening the project, running a first task.
*Exercise:* get the seed running and its tests passing, then land one small real change — fix the
untested code path or add a health-check view. Review the diff, commit it.
*Verification:* tests pass; a commit exists; the learner can state what the agent changed and why they accepted it.

### Module 1 — Judging output you didn't write
Reading a diff for what it does rather than what the summary claims. Running the tests before
believing the claim. Reproducing the bug before accepting the fix. Recognising plausible-but-wrong —
code that reads correctly and fails on an edge the agent never considered. Knowing when to stop the
agent rather than let it continue from a bad premise.

This is the discipline every later module compounds on, and the one earlier drafts of this design
assumed rather than taught.

*Exercise:* the course ships a **judgement set** — a handful of agent-produced diffs against the seed,
some correct, some subtly defective. Classify each as accept or reject, with evidence: a test run, a
traced failure path, or a cited criterion.
*Verification:* classifications match the answer key, **and** every rejection cites reproducible
evidence rather than suspicion. A correct verdict reached by hunch is scored as a miss — the evidence
is the skill being taught, not the verdict.

### Module 2 — Working agreement
Project instructions files: what belongs in them, what does not, why "be helpful" is worthless and
"run `python manage.py test` before claiming done" is not. `AGENTS.md` as the standard, per-tool
files as the exceptions, and how to avoid maintaining five near-identical files. Scope discipline.
Asking for verification rather than assurances.
*Exercise:* write an `AGENTS.md` for the sign-in project covering at minimum the test command, the
migration policy (generated, never hand-edited), where settings live, and project conventions.
Wire it up for the learner's tool. Demonstrate a behaviour change with and without it.
*Verification:* the file contains project-specific, checkable instructions — not generic advice that
would apply to any repository; the tool actually reads it; the learner can name the observed difference.

### Module 3 — Context management
What occupies context, what compaction or truncation costs, clearing as a routine rather than a
panic button, scoping reads to the parts of files that matter, and delegating side quests to keep
the main thread clean. Recognising the symptoms of a session that has lost the thread.
*Exercise:* implement sign-up and log-in. This is deliberately a sprawling multi-file Django task —
model or form, view, URL, template, tests, settings — the shape that reliably exhausts a context
window in any tool. Do it once naively, observe what happens, then re-run with context discipline.
*Verification:* sign-up and log-in work and are tested; the learner can name what filled context the
first time and which specific technique they applied the second.

### Module 4 — Models and token budgets
The most naturally vendor-agnostic module: every Tier 1 tool exposes a model picker spanning
multiple vendors. The current roster and what each model is for. Context window vs output cap vs
thinking budget — three different limits routinely confused for one. Where each tool exposes model
choice, and what a task costs before you run it.
*Exercise:* two tasks of different character against the same codebase — a mechanical one (back-fill
tests for the existing views) and a design one (choose an approach for password reset). Run each on
two models. Record quality, latency and cost.
*Verification:* a written comparison that defends a default for each kind of task, rather than stating a preference.

### Module 5 — Spec-driven development
Fully tool-independent. Brainstorm → spec → plan → implement → verify. Why the expensive mistakes
are the ones made before any code is written. How to tell a spec that constrains implementation from
one that merely describes a wish.
*Exercise:* take password reset through the full chain. The spec must state token expiry, single-use
semantics, the behaviour on an unknown email address, and what is covered by tests.
*Verification:* a spec file exists, contains no placeholders, its acceptance criteria are testable, and
the implementation matches it.

### Module 6 — Review that terminates
Why agent-driven review does not converge, and the rules that make it converge. Reviewing the diff
rather than the codebase. Severity tiers where only spec-traceable findings block. Freezing the
finding list after the first round. The ledger that stops settled items being re-raised. Bounded
rounds, and treating a third round as evidence the spec is wrong rather than the code.

Every Tier 1 tool can run this, because the contract is a document rather than a feature.

*Exercise:* write a `review-contract.md` for the sign-in project by adapting the course template,
then run a full review of the Module 5 password-reset work against it. Record the ledger. Fix the
blockers. Re-review.
*Verification:* **idempotence** — running the review twice against the same unchanged diff yields
the same verdict both times. Additionally: the review terminated in at most two fix rounds; every
blocking finding cites a spec criterion, a failing test or a documented convention; nits were
recorded without blocking; the final output is an explicit PASS or BLOCKED verdict rather than a
list of suggestions.

### Module 7 — Capstone
One feature of real substance — login rate limiting, or TOTP two-factor — with all six disciplines
applied: specified first, model chosen deliberately, context managed, implemented, then reviewed to
a terminating PASS against the learner's own review contract. Graded against a rubric drawn from the
preceding modules' criteria.

## The review contract

The course's most reusable artefact, shipped as `templates/review-contract.md` and adapted per
project. It exists because agent-driven review does not terminate by default: "is this good?" has
no answer, so each iteration produces fresh findings indefinitely.

Existing review guidance — including the `requesting-code-review` and `receiving-code-review`
skills already in this environment — defines severity tiers and how to push back on a wrong
reviewer, but **none defines a termination condition**. They tell a reviewer how to find issues,
never when to stop looking. That is the gap this contract fills.

### The seven rules

1. **Review the diff, not the codebase.** The reviewable unit is the change under review.
   Pre-existing problems outside it are recorded in a backlog file and never block.
2. **Only spec-traceable findings block.** A finding may block only if it cites a specific
   acceptance criterion from the spec, a failing test, or a documented convention in the project
   instructions file. Everything else is a nit: recorded, never blocking, never re-raised.
   **One labelled exception:** a security or data-loss defect blocks even when the spec is silent,
   provided a concrete exploitation or failure path is described. It is marked in the contract as an
   exception rather than a fourth kind of traceability, because it is the clause a reviewer will
   otherwise stretch into a general override.
3. **PASS is a legitimate and expected outcome.** The contract states this explicitly, because a
   reviewer that treats zero findings as failure will manufacture findings. The review's final
   line is a verdict — `PASS` or `BLOCKED (n blockers)` — not a list of suggestions.
   **Passing tests are a precondition for PASS**, not a finding: a change whose tests fail cannot
   pass regardless of how few issues were found, and a test suite that cannot be run yields `BLOCKED`.
4. **Findings freeze after round one.** Round one produces the complete list. Subsequent rounds
   verify only that those blockers were addressed, plus regressions introduced by the fixes
   themselves. No new hunting. This is the load-bearing rule; without it the others leak, because
   a second pass that goes looking will always find something.
5. **A ledger carries state across rounds.** Every finding is recorded with the status it has at
   the moment of discovery — `open`, `fixed`, `accepted as-is`, or `deferred to backlog` — so a
   fresh context cannot re-litigate what was settled. Only `open` findings survive a round.
6. **Two fix rounds maximum.** Still blocked after the second round means the specification is
   wrong or incomplete, not the code. Escalate to re-specification rather than continuing to review.
7. **Disagreement is resolved against the spec, not by seniority or politeness.** If the reviewer
   and the author disagree and the spec is silent, the finding is a nit by definition, and the
   silence is logged as a spec gap.

**When no written spec exists**, the review does not begin with the code. It begins by deriving three
to seven concrete, checkable criteria from whatever does exist — ticket, pull request description,
commit messages — and having the author confirm them. Once confirmed, that list is the spec for this
review and the rules apply normally. Without this step a traceability-only contract classifies almost
everything as a nit and degenerates into rubber-stamping, which is the opposite failure and a quieter
one. An unconfirmed derived list does not count; if the author will not confirm the criteria, that
disagreement is the finding.

### Why idempotence is the verification

Module 6's pass criterion is that the same unchanged diff reviewed twice yields the same verdict.
This is objective, tool-neutral, and tests precisely the property that is missing today. A review
process that cannot reproduce its own verdict has no verdict — it has opinions.

### Standalone value

The contract is written to be useful dropped into any project, by anyone who never took the course.
This is an explicit success criterion, and it makes the template the first piece of the course worth
building, since it pays for itself immediately.

## Duration and delivery

Roughly **18–20 hours hands-on** on the standard track, self-paced over three to four weeks.
The supervised track runs about 1.4× that, most of the difference landing in Modules 3, 5 and 7.

| Module | Hands-on | What drives the estimate |
|---|---:|---|
| 0 — First session | ~1h | Install, authentication, Django environment, seed green, one small change |
| 1 — Judging output you didn't write | ~1.5h | Working the judgement set, with evidence for each verdict |
| 2 — Working agreement | ~1.5h | Writing a genuinely specific instructions file takes iteration |
| 3 — Context management | ~3.5h | Sign-up and log-in implemented twice — naive, then disciplined |
| 4 — Models and budgets | ~2h | Two tasks across two models, plus the written comparison |
| 5 — Spec-driven development | ~3h | Password reset through the full chain, spec included |
| 6 — Review that terminates | ~2h | Writing the contract, then two review rounds plus the idempotence check |
| 7 — Capstone | ~3.5h | TOTP or rate limiting under full discipline, reviewed to PASS |

**Module 3's double implementation is the lesson, not padding.** Context exhaustion has to be
felt once to be believed. It is also the module most likely to need two sittings, and the
README should say so rather than letting learners think they have fallen behind.

**These are not coding hours.** The agent does the typing. The time goes into reviewing diffs,
iterating on instructions, and writing the comparisons and specs. The README states this
explicitly, because learners who expect to be typing conclude they are doing it wrong.

### Delivery shapes

- **Self-paced, one module per sitting, two to three weeks.** Recommended. The gap between
  sittings is where the practices meet the learner's real work, which is where they stick.
- **Cohort: eight two-hour sessions over four weeks.** Works with a facilitator; Module 3 needs the
  full slot and then some. This is also the natural shape for the supervised track, since the
  facilitator is the pair.
- **Intensive: two consecutive days.** Not recommended. Modules 3 and 7 are the ones fatigue damages
  most, and both land late. Never run the supervised track this way.

## Django-specific material, distributed

| Pattern | Where it lands |
|---|---|
| Test command, migration policy, settings layout | Module 2, as `AGENTS.md` content |
| Multi-file feature sprawl; ORM and settings as context traps | Module 3, as the core exercise |
| Mechanical test-writing vs design work as different model jobs | Module 4, as the two tasks |
| Migration and security criteria as testable acceptance criteria | Module 5, in the spec |
| Framework mechanisms over hand-rolled auth | Module 6, as blocking review criteria |
| Django security defaults as spec-traceable checks | Module 7, in the capstone rubric |
| Reading a Django diff for what it actually does | Module 1, as judgement-set material |

## The runner

**Skill name:** `agentic-onboarding`
**Description:** must start with "Use when…" per the repository's skill conventions.

**Behaviour, defined once in `runner-prompt.md`:**

1. On first invocation, help the learner copy the seed into a working directory, confirm the test
   suite passes, record which tool they are using, and place `progress.md`.
2. On each invocation, read `progress.md`, resume at the current module, teach from the module file,
   showing the mechanics row for the learner's recorded tool.
3. Set the exercise and stop. The learner does the work.
4. On return, verify: deterministic facts by inspection (do the tests pass, does the file exist, was
   there a commit, does the spec contain placeholders), everything qualitative judged against the
   module's written verification criteria.
5. Append a dated entry to `progress.md` recording what passed, what did not, and the specific gap.

**Hard rule:** the runner never edits the learner's code during an exercise. It may read anything and
explain anything. Doing the homework destroys the only signal the course has. The `reference/`
solutions exist for the author and for a genuinely stuck learner, and are offered only after a
failed attempt.

**Failure reporting is specific.** "Your AGENTS.md is too vague" is useless. "Lines 4–6 are generic
advice that would apply to any repository; nothing here tells the agent how to run your tests" is
the standard.

## Build constraints

**Volatile facts are sourced, never remembered — for all three Tier 1 tools.** Model identifiers,
context windows, pricing, limits, flag names, file conventions and feature availability are verified
against official documentation at build time. The README states the date the tool matrix was last
verified. This is now three times the volatile surface of a single-vendor course and is the main
ongoing maintenance cost of vendor neutrality.

**The AGENTS.md / CLAUDE.md split is the highest-churn fact in the course.** Re-verify first, every revision.

**Django version is pinned and stated.** The seed pins Django and Python in `requirements.txt`; the
README names the versions the course was written against.

**The runner owes a RED phase.** Per this repository's CLAUDE.md, every skill goes through
RED-GREEN-REFACTOR. Scenarios run against the module content with no runner present; the gaps
observed define what the runner is for and populate each module's Common Mistakes section.

**Content before mechanics.** The seed, the judgement set and modules 0–3 are written and tested
before the runner is built, so the runner is designed against real content.

**The judgement set needs an answer key that survives scrutiny.** Each defective diff must have a
reproducible failure — a test that fails, or a traced input that breaks it. A diff that is merely
stylistically worse does not belong in the set, because Module 1 grades evidence, not taste.

**Tier 1 parity is tested, not assumed.** Before release, the Module 2 and Module 3 exercises are run
end-to-end in each Tier 1 tool. A mechanics table written from documentation alone is a guess.

## Success criteria

1. A new engineer completes all eight modules **in any Tier 1 tool** and ends with a working Django
   sign-in application containing sign-up, log-in, password reset and the capstone feature — all tested.
2. Each module's exercise produces an artefact — a commit, an instructions file, a written comparison,
   a spec — and verification grades the artefact, never the tool.
3. No module contains a vague cross-tool instruction; every technique names a concrete mechanic per
   Tier 1 tool or declares the tool unsupported for it.
4. The runner works both as a Claude Code skill and as a prompt handed to another agent.
5. A review run under the course's contract terminates: the same diff reviewed twice yields the
   same verdict, and no review needs more than two fix rounds.
6. `templates/review-contract.md` is useful on its own, dropped into a project that never took the
   course.
7. Modules read correctly standalone, without any runner.
8. The seed's test suite passes on a clean checkout, on the pinned Django and Python versions.
9. Every defective diff in the judgement set has a reproducible failure, and a learner who accepts
   one can be shown exactly what they missed.
10. A junior on the supervised track completes the same exercises and the same verification as a
   senior on the standard track, differing only in pairing and pace.
11. No factual claim about tools, models, limits or pricing is sourced from memory.

## Open decisions

Settled: the course now lives in its own repository, `ai-on-boarding`.

None blocking. To revisit after the seed and modules 0–3 are drafted:

- Whether the capstone rubric warrants a machine-readable form, or stays prose.
- Whether Tier 1 should drop to two tools if parity testing proves expensive.
