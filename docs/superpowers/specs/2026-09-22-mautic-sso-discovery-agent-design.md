# Mautic SSO Discovery Agent — Design

Date: 2026-09-22
Source: [awais786/ai-on-boarding#82](https://github.com/awais786/ai-on-boarding/issues/82)

> **Post-implementation amendment (2026-09-23):** two decisions below were
> revised after this design was written, per direct instruction — this
> document is left as the historical record of the original design, not
> rewritten:
> - Every reference to reusing `GitHubClient` from `agents/issue-reconciler/`
>   (e.g. "Consumes: `GitHubClient` from `issue_reconciler.client`") is
>   superseded — this package now has its own self-contained
>   `mautic_sso_discovery/github_client.py`, with no cross-package
>   dependency, so its own SDD-generated pyproject/requirements never need
>   `agents/issue-reconciler` installed.
> - `claude-agent-sdk==0.1.0` (used throughout this doc's code) is stale —
>   the real current package is `claude-agent-sdk==0.2.158`, pinned in
>   `agents/mautic-sso-discovery/requirements.txt`.

## Goal

Build a Claude Agent SDK program that investigates a target codebase's current
authentication implementation, compares it against the (fixed) Moneta SSO/OIDC
contract, and produces a Markdown discovery report + SSO integration plan —
before any Mautic code is written, and before any GitHub issues are created.

This is the priority scope, taken directly from issue #82's requirements and
acceptance criteria. Two ideas raised in supporting Slack discussion —
building a Claude Code Skill wrapper, and making the Moneta side itself
swappable/dynamic — are explicitly out of scope for this pass (see
"Non-goals").

## Non-goals

- **Not** a generic "any SSO provider" tool. The Moneta contract is fixed and
  bundled into the agent, not fetched from a `--rules-repo` argument.
- **Not** a Claude Code Skill. The issue requires the Claude Agent SDK
  specifically (an unattended, scriptable agent), which a Skill (interactive
  Claude Code only) can't provide. A Skill wrapper may be worth building
  later but isn't part of this task.
- **Not** implementing the SSO integration itself. Output is a report and,
  gated on human review of that report, GitHub issues — never a Mautic PR.

## Reusability axis

One thing **is** parameterized: the target repository. The Moneta contract
is fixed for every run; the codebase being investigated against it is a CLI
argument, so reusing this agent for a future app #7 means passing a
different `--target-repo`, not changing code.

## Architecture

New package: `agents/mautic-sso-discovery/` (Python), mirroring the existing
`agents/issue-reconciler/` package layout (`pyproject.toml`, a module
directory, `tests/`).

Two CLI subcommands, corresponding to the two issue-mandated phases:

```
python -m mautic_sso_discovery discover \
  --target-repo https://github.com/pressingly/mautic \
  --out ./mautic-discovery-report.md

python -m mautic_sso_discovery propose-issues \
  --report ./mautic-discovery-report.md \
  --github-repo awais786/ai-on-boarding
```

### `discover`

1. Uses the Claude Agent SDK (`claude-agent-sdk`, Python) to run a session
   with tool access limited to `Read`, `Grep`, `Glob` — **no `Bash`,
   `Write`, or `Edit` tool is granted**, the model has no tool capable of
   modifying any file it can see. The clone itself is done by the
   orchestrating Python code (a plain `git clone --depth 1`) before the
   agent session even starts, not by the model calling a tool — cloning a
   repo has exactly one correct way to do it, so there's no judgment for
   the model to add, and it means step 2 below can run with zero window
   during which the model could act on a writable checkout.
2. Immediately after the clone, the orchestrating Python code runs
   `chmod -R a-w` on the cloned directory. This is the actual enforcement of
   "Agent must not modify the target repository" — a filesystem-level
   guarantee, not a prompt instruction the model could be talked out of.
3. The system prompt bundles the fixed Moneta SSO contract (see "Moneta
   requirements" below) and instructs the agent to:
   - Trace the target repo's real authentication flow — login, logout,
     users, sessions, roles/permissions, existing OAuth/OIDC — citing
     `file:line` evidence for every claim, using `Grep`/`Glob`/`Read` to
     verify rather than assume based on framework conventions.
   - Mark anything unverifiable as `ASSUMPTION` or `UNKNOWN` explicitly.
   - Compare traced reality against the bundled Moneta contract, identify
     gaps, and produce a proposed SSO integration architecture (auth flow,
     claims mapping, user/role provisioning, logout, session handling,
     security considerations) plus an actionable implementation-and-test
     plan referencing concrete files.
4. Output: a single Markdown file at `--out`. Local file only — not
   committed to this repo, not posted anywhere. The human reviews it before
   phase two runs.

### `propose-issues`

1. Separate, later invocation — this is the human gate. Nothing in
   `discover` triggers this phase; a person runs it deliberately after
   reading the report.
2. A second Agent SDK session, tool access limited to `Read` (on the report
   file only — no repo access, no GitHub access as a model tool). It drafts
   a structured list of issues: title, body, scope, affected files,
   acceptance criteria, tests, and dependency links between issues.
3. The orchestrating Python code (not the model) then creates each issue via
   GitHub's API in `awais786/ai-on-boarding`, reusing `GitHubClient` from
   `agents/issue-reconciler/issue_reconciler/client.py` rather than writing
   a new HTTP client. Keeping issue creation as plain code (not a model tool
   call) means a bad draft is a JSON diff to review, not a live API call to
   debug or roll back.

## Moneta requirements (bundled, fixed)

Copied as static reference files into `agents/mautic-sso-discovery/`,
sourced from `awais786/sso-rules-moneta` at the commit current as of this
design:

- `authentication.md` — TTLs, session-lifecycle contract, the "stale session
  on user switch" flush requirement.
- `apps-overview.md` — how the five existing apps consume
  `X-Auth-Request-Email`, gate local-auth UI under SSO, and structure logout.
- `openspec/specs/proxy-auth-middleware/spec.md` — the formal, scenario-level
  contract (bypass-path short-circuit, match/mismatch/no-session handling,
  auto-provisioning, email normalization, exact-match lookup) that any new
  app's middleware must satisfy.

These are committed alongside the agent code so the contract a given
discovery run used is versioned and reviewable, and future edits to the
upstream rules repo don't silently change past reports' basis.

## Safety summary

| Requirement (from issue #82) | Mechanism |
|---|---|
| Agent must not modify the target repo | `chmod -R a-w` after clone + no `Write`/`Edit` tool granted |
| Major findings need source evidence | Prompted requirement; report format reviewed for file:line citations before being treated as done |
| Assumptions/unknowns marked clearly | Prompted requirement; report format has explicit `ASSUMPTION`/`UNKNOWN` markers |
| Report generated as Markdown | `discover` phase's sole output artifact |
| Issues created only after report complete | Separate CLI subcommand, invoked manually, never chained from `discover` |

## Testing

The LLM's exploration choices aren't something to unit-test, but the
surrounding code is:

- CLI argument parsing (`discover`/`propose-issues`).
- The write-lockdown: a test clones (or fakes) a directory, runs the
  lockdown step, and asserts a subsequent write attempt fails.
- Parsing the drafted issue JSON into `GitHubClient` mutation calls —
  following the existing test pattern in `agents/issue-reconciler/tests/`.

## Open items for the implementation plan

- Exact Claude Agent SDK session configuration (model, permission mode,
  `allowed_tools` list) — resolved in the implementation plan.
- Exact Markdown report template/sections — resolved in the implementation
  plan, informed by issue #82's acceptance criteria list.
- Which GitHub auth token/env var `propose-issues` uses (likely the same
  `BOARD_TOKEN` pattern as `issue-reconciler`).
