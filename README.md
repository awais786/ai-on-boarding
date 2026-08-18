# ai-on-boarding

An onboarding course that takes an engineer from zero to competent daily driver of a coding agent —
Claude Code, Cursor or GitHub Copilot — plus the reusable artefacts the course produces.

Vendor-agnostic by design. Every discipline it teaches is a property of working with a coding agent,
not of any one product.

## Status

**Design stage.** The specification is written; the course itself is not built yet.

| | |
|---|---|
| [`docs/specs/2026-08-18-agentic-coding-onboarding-design.md`](docs/specs/2026-08-18-agentic-coding-onboarding-design.md) | ✅ The full design |
| [`templates/review-contract.md`](templates/review-contract.md) | ✅ Usable today, standalone |
| `seed/`, `judgement-set/`, `modules/`, `runner-prompt.md` | ⬜ Not built |

## Use the review contract today

It stands alone. You do not need the course, and the course does not need to exist.

Agent code review does not converge: asked "is this good?", an agent always finds something, because
any code can be improved indefinitely. The contract replaces that with "does this meet the spec?" — a
question with an answer, and therefore an end.

```bash
cp templates/review-contract.md /path/to/your-repo/
```

Fill in the **Project settings** block at the bottom — spec location, test command, ledger path. Then:

```
Review the current diff against @review-contract.md
```

To make it automatic, add one line to your project instructions file — `CLAUDE.md` for Claude Code,
`AGENTS.md` for everything else:

> Code review follows `review-contract.md`. Do not review outside that contract.

Expect the first review to feel too permissive. Things you would normally fix get logged as nits and
pass. That is the price of termination, and it is deliberate.

## The course

Eight modules, ~19–21 hours hands-on, self-paced over three to four weeks. Every exercise runs against
one Django sign-in application the learner builds across the course, starting from a shipped seed.

| # | Module | Exercise |
|---|---|---|
| 0 | First session: asking and running | Seed green, then one change made twice — vague prompt vs scoped prompt |
| 1 | Judging output you didn't write | Classify a set of agent diffs — with evidence, not hunches |
| 2 | Working agreement | Write an `AGENTS.md`, demonstrate a behaviour change |
| 3 | Context management | Sign-up + log-in implemented twice — naive, then disciplined |
| 4 | Models and token budgets | Two tasks × two models, defended default |
| 5 | Spec-driven development | Password reset through the full chain |
| 6 | Review that terminates | Write a review contract, review Module 5's work against it |
| 7 | Capstone | TOTP or rate limiting, reviewed to a terminating PASS |

**Tier 1 tools** — full mechanics, parity-tested exercises: Claude Code, Cursor, GitHub Copilot.
**Tier 2** — mapping tables only: Windsurf, Codex, Aider, Gemini CLI.

### Two tracks

One body of content. Seniority changes delivery, not substance.

- **Standard** — solo and self-paced. Assumes working Django familiarity.
- **Supervised** — for juniors. Same modules, same verification; Modules 3, 5, 6 and 7 are paired
  with an experienced reviewer, and the pair satisfies the Django prerequisite. About 1.4× the duration.

The real prerequisite is not Django. It is the ability to evaluate code you did not write — which is
why Module 1 now teaches it directly instead of assuming it.

## Build order

Seed → judgement set → modules 0–3 → runner skill → modules 4–7 → Tier 1 parity testing.

The runner comes late on purpose: it should be designed against real content rather than an imagined shape.
