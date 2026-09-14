# Issue Reconciler — Build Plan

Repo: `awais786/ai-on-boarding`
Board: user-level Projects v2, project #1 "Tickets Allocation"

## Goal

An agent that sweeps the board, determines whether each open issue already has
work in flight (a PR, or an OpenSpec proposal), and moves the board status
accordingly — without ever duplicating work or overriding a human.

**Naming.** This is a reconciler, not a triage agent. It does not categorize
incoming work; it observes actual state in the repo, compares it to the state
recorded on the board, and converges the two. The `needs-triage` label is the
one place the old word is correct — when the agent cannot decide, it is
genuinely handing the issue to a human for triage.

## Architecture: hub-and-spoke

A single hub owns issue selection, leasing, decision-making, and all writes.
Read-only spokes gather evidence in parallel and return structured JSON.

**Why not sequential:** the work is a wide fan-out over N independent issues.
A pipeline makes issue #40 wait on issue #12, and one slow API call stalls the
batch.

**Why not peer-to-peer:** there is no arbiter, so two agents can claim the same
issue. Avoiding duplicate work is the core requirement, and P2P negotiation
removes the single owner that makes it structurally impossible.

**Why hub-and-spoke:** fan-out is naturally parallel, spokes share no state,
and all mutation authority lives in one place — one writer, one audit trail,
one rate limiter.

Within each spoke the work is a short sequential chain (fetch → normalize →
score). Hub-and-spoke at the top, sequential inside.

## Hard constraints

1. **The model never touches the API.** No tool use, no MCP, no shell. Code
   fetches, the model receives normalized JSON, the model returns a verdict,
   code writes. Issue and PR text is untrusted input — injection can produce a
   bad verdict but never a bad action.
2. **Spokes return evidence, not decisions.** A spoke reports "PR #88
   references this issue, merged, confidence 0.9". It never says "close this".
3. **Policy is deterministic code.** No model call decides a transition. The
   model's only job is fuzzy matching a PR to an issue when there is no
   explicit reference.
4. **One writer.** Only `writers/board.ts` mutates anything.
5. **No silent transitions.** Every status change is preceded by a comment
   stating the evidence. If the comment fails, abort the transition.

## Verified environment

| Thing | Value |
|---|---|
| Project ID | `PVT_kwHOA4V_f84AGZiK` |
| Status field ID | `PVTSSF_lAHOA4V_f84AGZiKzgDsBxo` |
| Option: Todo | `f75ad846` |
| Option: In Progress | `47fc9ee4` |
| Option: Done | `98236657` |

Note the board uses **Done**, not "Closed".

**Auth:** `GITHUB_TOKEN` cannot access Projects v2. Requires a classic PAT with
`repo` + `project` scopes, stored as repo secret `BOARD_TOKEN`.

**Board scope warning:** the board is user-level and may contain items from
other repos. The selector must filter on `repository.name == "ai-on-boarding"`.

## Layout

```
agents/issue-reconciler/
  index.ts                 # entrypoint
  config.ts                # board IDs, filters, thresholds
  orchestrator.ts          # selection, leasing, fan-out, run log
  api/
    client.ts              # auth, retry, backoff, rate-limit
    fetchers/
      board.ts             # project items + current status
      issues.ts            # open issues + labels
      prs.ts               # linked PRs via timeline
      repo.ts              # openspec/changes/ contents
      timeline.ts          # labeled/unlabeled events + actors
  spokes/
    pr-evidence.ts
    openspec-evidence.ts
    board-history.ts
  matcher/
    fuzzy.ts               # the only model call
  schemas/
    evidence.schema.json
  policy/
    rules.ts               # pure functions
  writers/
    board.ts               # sole write authority
  state/
    leases.ts
    runlog.ts
  fixtures/
    issues-snapshot.json
```

## Contracts

```ts
type LinkedPR = {
  number: number;
  title: string;
  state: 'OPEN' | 'CLOSED' | 'MERGED';
  merged: boolean;
  mergedAt: string | null;
  isDraft: boolean;
  headRefName: string;
  matchSource: 'explicit' | 'fuzzy';
  confidence: number;          // 1.0 for explicit
};

type Evidence = {
  issueNumber: number;
  itemId: string;              // project item ID
  currentStatus: string | null;
  hasIgnoreLabel: boolean;
  linkedPRs: LinkedPR[];
  openSpecProposals: string[];
  lastStatusActor: string | null;
  lastStatusAt: string | null;
  transitionCount: number;     // agent flips in last 7 days
};

type Decision =
  | { action: 'set_done' }
  | { action: 'set_in_progress' }
  | { action: 'flag'; reason: string }
  | { action: 'noop'; reason: string };
```

## Policy rules

Evaluated in order. First match wins.

```
1. hasIgnoreLabel                        -> noop  ("ignore label")
2. lastStatusActor is human
   AND lastStatusAt within 24h           -> noop  ("human override")
3. transitionCount >= 3                  -> flag  ("flapping")
4. any PR merged AND no PR open          -> set_done
5. merged AND open PRs both present      -> flag  ("mixed PR states")
6. any PR open (incl. draft)             -> set_in_progress
7. openSpecProposals non-empty           -> set_in_progress
8. only fuzzy matches below threshold    -> flag  ("low confidence")
9. otherwise                             -> noop  ("no evidence")
```

Rules 5 and 6 were swapped from an earlier draft: PR state is mutually exclusive
per PR (OPEN, CLOSED, or MERGED), so "merged AND open both present" only
happens across *different* linked PRs. With "any PR open" checked first, that
case always matched rule 6 before rule 5 could ever fire, making the
mixed-state flag dead code. Checking the mixed case first makes both rules
reachable and routes the ambiguous case to a human instead of silently
resolving it as in-progress.

Fuzzy confidence threshold: start at 0.85. Explicit references
(`Closes #N`, linked PR, `CrossReferencedEvent`) bypass the model entirely.

`flag` means: apply `needs-triage` label, post a comment with the evidence,
change no status.

## Commenting

Comment first, then mutate. If the comment fails, abort — no silent state
changes, and the comment is the forensic trail when something goes wrong.

Evidence only. No reasoning prose, no hedging.

```
Done — PR #88 merged 2026-09-14.
Matched via: closing reference in PR body.
Run: 2026-09-14T17:32Z · [logs](...)
```

Fuzzy matches must say so and include the confidence, since that is the case a
human most needs to audit:

```
Done — PR #91 merged 2026-09-13.
Matched via: title similarity (confidence 0.89). No explicit reference found.
If this is wrong, add `agent:ignore` and reopen.
Run: 2026-09-14T17:32Z · [logs](...)
```

Every comment carries a machine-readable fingerprint in an HTML comment. This
is how `board-history` identifies the agent's own writes without needing a
distinct bot identity, which also resolves the actor-identity question when
running under a PAT.

```html
<!-- issue-reconciler: v1 run=abc123 decision=set_done evidence=sha256:... -->
```

Rules:

- `noop` never comments. A 30-minute cron must not turn every issue into a wall
  of "still nothing to report".
- `flag` always comments — a human has to act, so the comment is the point.
- One comment per transition, not per run. Check the idempotency key before
  commenting, not just before writing.
- Comment on `set_in_progress` during the trust-building period; revisit later,
  since it is lower stakes and more frequent, and the most likely source of
  noise.

## Reliability

- **Lease per issue** with TTL before dispatch, released after write. Stored in
  `state/leases.ts` (repo-level Actions cache or a committed JSON file).
- **Idempotency key** `hash(issueNumber + evidence)`. If unchanged since last
  run, skip entirely — no model call, no write, no comment.
- **Read-then-write tight.** Projects v2 has no compare-and-set, so re-read
  current status immediately before mutating and abort if it moved.
- **Ordering.** Set board status first, then close the issue. If the close
  fails, the board is already correct and the next run reconciles.
- **Error taxonomy:** transient → retry with jitter; schema → one repair retry
  then quarantine to DLQ and continue batch; ambiguous → flag; fatal → halt
  writes and alert.
- **Circuit breaker:** if >20% of the batch errors, stop writing.
- **Cost guard:** per-run cap on model calls. Exceeding it halts the batch and
  logs. Protects against a bug defeating the idempotency check.
- **Startup validation:** resolve the board field and option IDs. Fail loudly
  if any no longer exist rather than writing garbage.

## Workflow

`.github/workflows/issue-reconciler.yml` — thin. Installs deps, calls one
entrypoint. All logic in TypeScript so it can be tested.

```yaml
on:
  schedule:
    - cron: '*/30 * * * *'
  pull_request:
    types: [closed]
  workflow_dispatch:
    inputs:
      dry_run:
        default: 'true'

permissions:
  contents: read
  pull-requests: read
  issues: write

concurrency:
  group: issue-reconciler
  cancel-in-progress: false
```

Board writes use `secrets.BOARD_TOKEN`, not `GITHUB_TOKEN`.

The `pull_request: closed` path processes only issues referenced by that PR,
not the whole board — it exists so a merge reflects in seconds instead of up to
30 minutes.

Use a `concurrency` group distinct from the existing PR review agent so the two
don't queue behind each other.

## Build order

Each phase should be independently testable.

**Phase 1 — policy engine (no network).**
Implement `policy/rules.ts` as pure functions. Unit test against
`fixtures/issues-snapshot.json`. This is the part that determines whether the
agent is trustworthy; build it before anything can write.

**Phase 2 — fetchers and spokes.**
Build `api/` and `spokes/` to produce the `Evidence` shape the rules already
expect. Single GraphQL query per issue batch, not per issue. Normalize before
returning — drop URLs, avatars, node IDs; truncate bodies.

**Phase 3 — fuzzy matcher.**
Only called when there is no explicit PR reference. Strict JSON schema on
output, one repair retry, then treat as no match. Haiku is likely sufficient.

**Phase 4 — orchestrator.**
Selection filters, leasing, bounded concurrency, run log.

**Phase 5 — writer, dry-run only.**
Posts a comment saying what it *would* do. No mutations. Run for a week.

**Phase 6 — enable writes.**
`set_done` first (lower risk, clearer signal), then `set_in_progress`.

## Acceptance criteria

- Two concurrent runs never produce duplicate transitions
- A re-run with unchanged evidence performs zero writes and zero model calls
- Malformed spoke output does not abort the batch
- A human status change within 24h is never overridden
- `agent:ignore` is always respected
- Board items from other repos are never touched
- Policy rules pass fixture-based tests with no network access
- Every write has a corresponding run-log entry with the evidence that caused it
- No status change occurs without a preceding comment
- A failed comment aborts the transition rather than proceeding silently
- Repeated runs over unchanged evidence produce exactly one comment total

## Out of scope

Creating PRs, closing issues without PR evidence, editing issue bodies,
reopening closed issues, modifying any board field other than Status.

## Open questions

- Where does OpenSpec live in this repo? `contents/openspec/changes` returned
  nothing — confirm the path before building that spoke.
- Actor identity is resolved for now by the comment fingerprint above. A GitHub
  App would give a distinct bot identity and remove the need for fingerprint
  parsing — worth revisiting once the agent is out of dry-run, not a blocker.
