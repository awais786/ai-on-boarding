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
3. **Policy is deterministic code.** No model call decides a transition
   directly. The four reasoning spokes (below) each produce a structured
   verdict over evidence they're handed; `rules.py` is still the only place
   that turns verdicts into a Done/In Progress/Flag/Noop decision.
4. **One writer.** Only `writers.py` mutates anything.
5. **No silent transitions.** Every status change is preceded by a comment
   stating the evidence. If the comment fails, abort the transition.

## Fuzzy PR matching — removed

An earlier draft added a model call to guess whether an unlinked PR resolves
an issue, by title similarity. Dropped: the team's actual convention is that
every PR description must reference an issue number, so an "unlinked PR"
that really resolves something shouldn't exist. The real gap this was
covering for was narrower - GitHub only treats a reference as
`willCloseTarget: true` when the PR uses a specific closing keyword (Closes,
Fixes, Resolves), so a PR that mentions `#47` without one of those words was
being silently ignored. Fixed deterministically instead: `fetch_linked_prs`
(`github.py`) now accepts any cross-reference to the issue, not only
closing-keyword ones. Still `match_source: "explicit"`, still zero model
calls. Tradeoff: a PR that merely mentions `#47` in passing (not actually
resolving it) now also counts as evidence - accepted, since the convention
makes that rare.

## AI reasoning spokes

Four spokes that each answer one judgment call a lookup can't, run in
parallel per issue alongside the existing deterministic ones, all feeding
into per-issue synthesis:

1. **Completion check** - do this issue's linked PR(s) together fully
   resolve it, or only partially?
2. **Activity check** - is an open linked PR still active, blocked, or
   abandoned (commit/review recency)?
3. **Reference validation** - does the PR's `#N` reference actually match
   this issue's intent, or is it a wrong/copy-pasted number?
4. **Stale/superseded check** - has the linked PR been superseded by later
   work that solves the same problem differently?

Each is one model call producing a strict-schema verdict (same shape as the
former fuzzy matcher: JSON schema out, no tool use, no API access from the
model). Cost is accepted - no per-run cap needed the way the fuzzy matcher
had one, since these only run for issues that already have a linked PR to
reason about, not the whole board.

**Synthesis**, per issue: merges the existing deterministic evidence *and*
the four verdicts into one `Evidence`-like record, then hands it to
`rules.py`. Where a verdict actively disagrees with the raw evidence (e.g.
completion check says "PR merged but issue not fully resolved" against a
merged linked PR), synthesis routes to `flag` rather than letting `rules.py`
choose a side no human has confirmed - the model can only ever demote a
transition to human review, never upgrade one.

## Run summary and Slack

After every issue in the run is synthesized and written, the hub rolls all
of that run's decisions + rationale into one summary and posts it once to a
Slack channel (`SLACK_WEBHOOK_URL` secret, plain `requests.post`). `noop`
issues are omitted from the summary the same way they're omitted from
comments - the summary reports what changed, not the whole board.

## Concurrency fix

The evidence-gathering calls in `orchestrator.py` (`fetch_linked_prs`,
`gather_board_history`, `gather_openspec_proposals`, and now the four
reasoning spokes) currently run as sequential blocking calls, not the
"spokes gather evidence in parallel" the architecture section promises above
- each one used to be a single independent Python call, so it didn't matter
until reasoning spokes made each one slow enough for the gap to be real.
Fixed alongside adding the reasoning spokes: a thread pool per issue's
evidence phase, same pattern `orchestrator.py` already uses for concurrency
across issues.

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

The plan originally specified TypeScript. Rewritten in Python partway through
implementation (Phase 5, mid-build) for consistency with the rest of this
repo (Django, the pr-review agent) - see "Language and tooling notes" below
for the choices that changed along with it.

Went through two shapes after the original per-concern subpackage split
(`api/fetchers/`, `spokes/`, `matcher/`, `policy/`, `writers/`, `state/` -
each holding one or two small files plus an empty `__init__.py`, more
ceremony than the project's size earned): first flattened to one file per
concern at the package root, then partly re-nested into two subpackages
once the root grew past a dozen files - `io/` for everything that talks to
GitHub, `ai/` for the model-calling layer. No `ruff.toml` - linting isn't
run on this project.

```
agents/issue-reconciler/
  pyproject.toml
  requirements.txt
  issue_reconciler/
    __main__.py              # entrypoint: python -m issue_reconciler
    config.py                # board IDs, filters, thresholds
    types.py                 # LinkedPR / Evidence / Decision TypedDicts
    hashing.py               # comment fingerprint + evidence idempotency hash
    rules.py                 # the policy engine, pure functions
    orchestrator.py          # selection, leasing, fan-out, run log
    state.py                 # leases + run log (JSON-backed)
    slack.py                 # end-of-run summary posted once, not per issue
    io/                      # everything that talks to GitHub
      client.py              # GraphQL client: auth, retry, backoff, rate-limit
      github.py              # every fetch from GitHub + the two evidence spokes
      writers.py             # the sole write authority: comment + mutations
    ai/                      # everything that talks to the model
      reasoning.py           # the four reasoning spokes (completion, activity,
                              # reference validation, stale/superseded)
  tests/
    support.py                # fake transports (no live credentials in tests)
    fixtures/
      issues_snapshot.json
    test_*.py                 # one file per source module, same name
```

## Contracts

TypedDicts in `issue_reconciler/types.py`, snake_case fields (translated
1:1 from the original TS shapes):

```python
class LinkedPR(TypedDict):
    number: int
    title: str
    state: Literal["OPEN", "CLOSED", "MERGED"]
    merged: bool
    merged_at: str | None
    is_draft: bool
    head_ref_name: str
    match_source: Literal["explicit", "fuzzy"]
    confidence: float          # 1.0 for explicit


class Evidence(TypedDict):
    issue_number: int
    item_id: str                # project item ID
    current_status: str | None
    has_ignore_label: bool
    linked_prs: list[LinkedPR]
    open_spec_proposals: list[str]
    last_status_actor: str | None
    last_status_at: str | None
    transition_count: int       # agent flips in last 7 days


class Decision(TypedDict):
    action: Literal["set_done", "set_in_progress", "flag", "noop"]
    reason: str
```

## Language and tooling notes

- **Python, not TypeScript.** Matches `claude-pr-review/`, the only other
  agent in this repo. `agents/issue-reconciler/.venv` mirrors
  `claude-pr-review/.venv`; `pip install -e .` makes `issue_reconciler`
  importable from `tests/`.
- **`requests` against the GraphQL endpoint directly, not the `gh` CLI.**
  `claude-pr-review/pr_review/ci/github.py` shells out to `gh api` for
  everything, but Projects v2 needs a classic PAT (`BOARD_TOKEN`) distinct
  from the `gh` CLI's own auth, and `client.py`'s retry/backoff/rate-limit
  logic is far more controllable over a direct HTTP call than over a
  subprocess. This is a deliberate divergence from the sibling's
  convention, not an oversight.
- **Raw JSON schema dicts for structured output, not Pydantic.** Matches
  `claude-pr-review/pr_review/core/agent.py`'s
  `output_config={"format": ...}` + manual `json.loads()` pattern exactly,
  rather than `client.messages.parse()` + a Pydantic model. Also sidesteps a
  real bug the TS version hit: `zodOutputFormat().parse()` throws on a
  schema mismatch instead of returning `parsed_output: None`, contradicting
  its own docs. Doing the JSON parse and shape validation by hand in
  `fuzzy.py` makes the retryable case (bad JSON, wrong shape) and
  the non-retryable case (a real `anthropic.APIError` from `create()`
  itself) impossible to conflate - there is no ambiguous exception
  hierarchy to get wrong.
- **`ThreadPoolExecutor`, not asyncio.** The GitHub/Anthropic clients here
  are synchronous, and threads match `orchestrator.py`'s I/O-bound fan-out
  without an async rewrite of every fetcher. Real OS threads mean the
  shared state a single-threaded TS event loop got for free (leases, the
  run log, the model-call counter, the circuit breaker) can genuinely race
  between threads - `orchestrator.py`'s `_RunState` guards all of it behind
  one lock, with only the network calls themselves running outside it.

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

- `noop` never comments. A recurring cron run must not turn every issue into a
  wall of "still nothing to report".
- `flag` always comments — a human has to act, so the comment is the point.
- One comment per transition, not per run. Check the idempotency key before
  commenting, not just before writing.
- Comment on `set_in_progress` during the trust-building period; revisit later,
  since it is lower stakes and more frequent, and the most likely source of
  noise.

## Reliability

- **Lease per issue** with TTL before dispatch, released after write. Stored in
  `state.py` (repo-level Actions cache or a committed JSON file).
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

`.github/workflows/issue-reconciler.yml` — thin. Installs deps from
`requirements.txt`, calls one entrypoint. All logic in Python so it can be
tested with pytest.

```yaml
on:
  schedule:
    # 00:00 PKT daily (Pakistan is UTC+5, no DST -> 19:00 UTC)
    - cron: '0 19 * * *'
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
not the whole board — it exists so a merge reflects in seconds instead of
waiting for the next daily cron run.

Use a `concurrency` group distinct from the existing PR review agent so the two
don't queue behind each other.

## Build order

Each phase should be independently testable.

**Phase 1 — policy engine (no network).**
Implement `rules.py` as pure functions. Unit test against
`fixtures/issues_snapshot.json`. This is the part that determines whether the
agent is trustworthy; build it before anything can write.

**Phase 2 — fetchers and spokes.**
Build `github.py` to produce the `Evidence` shape the rules already expect.
Single GraphQL query per issue batch, not per issue. Normalize before
returning — drop URLs, avatars, node IDs; truncate bodies.

**Phase 3 — fuzzy matcher.**
Only called when there is no explicit PR reference. Strict JSON schema on
output, one repair retry, then treat as no match. Haiku is likely sufficient.

The original plan never specified where the matcher's candidate PRs come
from - the linked-PR fetcher only returns explicit references, which by
definition don't exist for an issue that reaches the matcher. Resolved by
adding a candidate-PR fetch to `github.py`: one repo-wide query per run (not
per issue) for open PRs plus PRs merged in the last
`FUZZY_CANDIDATE_LOOKBACK_DAYS` days, capped at `FUZZY_CANDIDATE_LIMIT` each.
The orchestrator fetches this pool once and passes it to every issue that
needs fuzzy matching.

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
