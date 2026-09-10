# pr-review-agent

A three-layer automated PR review. Layer 1 is deterministic tooling; Layers 2 and 3 are Python
agents calling the Claude API directly (`anthropic` SDK) - not the Claude Code CLI.

| Layer | What | Model | Where |
|---|---|---|---|
| 1 | Lint the files the PR changed. Mechanical, always right about what it covers. | - | `lint.py` |
| 2 | Judge the diff for architectural fit, convention compliance, correctness/completeness, and blast radius (duplicated logic elsewhere in the repo). Runs Layer 1 itself first; drops any of its own findings that land on the same file/line as a Layer 1 finding - in code, not by prompt instruction. | `claude-sonnet-5` | `judge.py` |
| 3 | Independently re-check every Layer 2 finding's citation and failure scenario before it can block a merge, one finding per agent call. Drops or downgrades anything that doesn't hold up. | `claude-haiku-4-5-20251001` | `verify.py` |
| 4 | Render Layer 3's output as the `Ready to merge: yes/no` verdict, per this repo's review contract: a finding blocks only if it still carries a citation. Exits non-zero on `no`, for CI. | - | `gate.py` |

## Running it

```bash
cd claude-pr-review
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Needs an Anthropic credential - ANTHROPIC_API_KEY, or `ant auth login`.
export ANTHROPIC_API_KEY=...

# Layer 1, standalone:
.venv/bin/python lint.py [pr-number|branch]        # omit for the working tree

# Layer 2:
.venv/bin/python judge.py [pr-number|branch] --out build/findings.json

# Layer 3, given Layer 2's output:
.venv/bin/python verify.py [pr-number|branch] --findings build/findings.json --out build/verified_findings.json

# Layer 4, given Layer 3's output:
.venv/bin/python gate.py --findings build/verified_findings.json --out build/verdict.md
```

All three accept the same target: a PR number, a branch name, or nothing (the working tree's
uncommitted and staged changes). `target.py` resolves it the same way for every layer, so they
never silently disagree about which files or diff make up "the PR".

## How Layer 2 and 3 work

Both are a manual agentic loop (`agent.py`) over `client.messages.create()`: the model gets
read-only tools (`read_file`, `grep`, `list_files` - `tools.py`, confined to the repo root) to
search the codebase, and every request also carries `output_config.format` with a JSON schema
(`agent.py`'s `FINDINGS_SCHEMA`) that constrains the model's *final* text answer. Tool-use turns are unaffected -
the schema only binds once the model stops calling tools and writes a final answer - so this
gets both agentic search and guaranteed-valid JSON output from a single loop, with no markdown
fence or explanatory prose to strip afterward.

Each agent's system prompt lives in its own file under `prompts/` (`judge.md`, `verify.md`),
read from disk at import time rather than embedded as a Python string - the same reason the
review instructions previously lived in their own `SKILL.md` files: editable and reviewable on
their own, without touching the orchestration code around them.

A manual loop was used instead of the SDK's beta `tool_runner` specifically so `output_config`
and `tools` could be combined without relying on undocumented interaction between two beta
surfaces.

The initial user message (repo rules + diff, which stays constant across the loop) carries
`cache_control: {"type": "ephemeral"}`, which also covers `tools` and the system prompt ahead of
it. As the loop appends tool-call and tool-result turns, the breakpoint moves forward to the
newest block each iteration (clearing the previous one, to stay under the 4-breakpoint cap) -
otherwise only the very first turn would ever be cached, and every later turn would resend the
whole growing tail at full price, the cost of which grows with roughly the square of the number
of turns.

Retries for transient API errors (429/5xx/connection failures) and tool-output truncation
(`MAX_OUTPUT_CHARS` in `tools.py`) are already handled - the SDK client retries by default
(`max_retries`), so `agent.py` doesn't reimplement it.

`judge.py` also passes `task_budget=TASK_BUDGET_TOKENS` (40,000) to `agent.run()` - a total
token ceiling for the whole loop (beta `task-budgets-2026-03-13`), so the model paces its own
spend across iterations (reading fewer/more files depending on what a given diff needs) instead
of every response getting the same fixed `MAX_TOKENS` cap regardless of how much the turn
actually required. `agent.run()`'s `task_budget` argument is opt-in per caller because the beta
isn't supported on every model - `verify.py` runs on Haiku 4.5, which doesn't support it, so it
stays on the plain (non-beta) request path and keeps `MAX_ITERATIONS`/`MAX_TOKENS` as its only
spend guardrail.

`agent.run()` splits its input into `stable_content` (cached) and `variable_content` (not,
appended after it uncached). `verify.py` calls `agent.run()` once per finding rather than once
for the whole batch - a live test found the batched version had no way to stop one hard-to-verify
finding from consuming the entire tool-use budget and starving every other finding in the same
call (see `## Verifying one finding per call` below). Since every one of those per-finding calls
for a given PR shares the same diff+rules, that content goes in as `stable_content` so it's cached
across calls and only the single varying finding is billed at full price each time - the
alternative (repeating the whole diff+rules at full price on every call) would have made
per-finding verification meaningfully more expensive than the batched version it replaced.

## Verifying one finding per call

`verify.py` used to send Layer 2's whole findings list in a single `agent.run()` call. Live
testing against a real PR (5-finding batch, Haiku 4.5) found three distinct failure modes across
successive attempts to fix it by editing `prompts/verify.md` alone: the loop exceeded
`MAX_ITERATIONS` without finishing; after raising the cap and adding a budgeting instruction, it
spent nearly the whole budget re-running one "does anything reference this file" search with
rephrased patterns nine times while never properly checking the other four findings; after adding
an explicit numeric per-finding budget, it overcorrected to zero tool calls and silently dropped
every finding, including two real CRITICAL ones. Each prompt fix for one failure mode pushed the
model toward another - a single batched call has no structural way to stop one hard finding from
consuming the shared budget and affecting every other finding in the same response.

Splitting to one `agent.run()` call per finding removes the failure mode at the architecture
level rather than continuing to word around it: each finding gets its own fresh
`MAX_ITERATIONS`, and a stuck or wrong verification on one finding cannot affect any other.
`prompts/verify.md` was rewritten for a single finding per call to match - the batch-budgeting/
starvation language is gone since the problem it addressed no longer exists in this shape. It was
also restructured into two explicit, ordered questions (is the concern real, then separately is
the citation good) after a fixture test showed a weak-but-real citation could drag a whole valid
finding down with it - citation quality can now only ever edit a finding's `citation`/`severity`/
`summary` fields, never remove it from the output.

A finding whose verification call itself fails (a transient API error, or the loop exhausting
`MAX_ITERATIONS`) is **kept**, not dropped - with `citation` cleared (so it can never block a
merge on unverified grounds) and its summary prefixed `[UNVERIFIED - Layer 3 could not run]`. A
five-file live test lost a real privilege-escalation finding to a transient 500 under the
original "drop on error" policy; a random infrastructure hiccup is not evidence against a
finding, so it now degrades to a visible, non-blocking nit instead of disappearing from the
report. `file`/`line` anchors are preserved either way - `verify.py` never touches them, since
Layer 4 renders a finding by them.

## Testing verify.py without a live PR

`eval_verify.py` runs `verify.verify()` against a saved fixture (a directory with `diff.txt`,
`rules.json`, `findings.json`, and `files/`) instead of a real PR - useful for iterating on
`prompts/verify.md` without needing a paid CI cycle each time (it still spends real API money
per trial - it's the round-trip through GitHub Actions and a throwaway PR that's avoided, not the
API call itself). `fixtures/debug-files/` was captured from a real `judge.py` run against a
throwaway smoke-test PR (three deliberately flawed files: a hardcoded secret, a plaintext-password
print, a duplicated validator). Add more fixture directories in the same shape to cover other
scenarios.

`files/` matters because Layer 3 reads the *working tree* through `tools.py`, not the fixture's
own diff text - an early version of this harness shipped without it, so every `read_file` against
a file the fixture's diff added returned "No such file", Layer 3 concluded the described code
didn't exist, and dropped findings for that reason rather than any reason the fixture was written
to test. `eval_verify.py` stages `files/`'s contents into the repo for the run and removes them
afterward (refusing to overwrite anything that already exists there), so the tree Layer 3 sees
matches the diff it was handed.

```bash
.venv/bin/python eval_verify.py fixtures/debug-files --trials 3
```

## Why this shape

- **Layer 1 is not an agent call.** A linter is never wrong about what it covers, so there's no
  reason to spend a model call re-deriving what `ruff` already knows deterministically. `judge.py`
  calls `lint.run()` directly as a Python function, not a subprocess or a tool the model invokes.
- **Layer 2 excludes Layer 1's findings by `(file, line)`, in code.** An earlier version of this
  system asked the model not to repeat Layer 1's findings via a prompt instruction; testing found
  that alone wasn't reliable - the model restated a lint finding as its own once. `judge.py` now
  filters the model's output against Layer 1's `(file, line)` set after the call returns, which
  cannot fail to hold the way a prompt instruction can be ignored.
- **Layer 3 exists because Layer 2's output is free-form**, not a fixed check list - a fabricated
  or misapplied citation is possible in a way it isn't for a linter, so it gets independently
  checked against the actual diff and repo before it's allowed to block anything.
- **Both agents get read-only tools only** (`read_file`, `grep`, `list_files`, each confined to
  the repo root with path-traversal checks) - no write, no shell beyond those three functions, so
  neither can modify the repo or do anything beyond reading it and reporting.

## CI

`.github/workflows/pr-review-agent.yml` runs all four layers on every PR (`opened`,
`synchronize`) against `secrets.ANTHROPIC_API_KEY`, posts Layer 4's verdict as a PR comment via
`gh pr comment`, and fails the check when the verdict is `no`.

## What's been tested

Local (`eval_verify.py fixtures/debug-files --trials 5`, valid fixture, 5 repeated trials): the
CI-visible verdict (`Ready to merge: no`) was stable across all 5, with per-finding disposition
varying underneath - the two CRITICAL security findings survived 5/5, the two MAJOR process
findings 3/5-4/5, and zero `file`/`line` mutations.

Live, end to end via `.github/workflows/pr-review-agent.yml` against a throwaway PR: Layer 2
raised 4 findings, Layer 3 kept 3 with all iterations inside the 30-turn cap, and Layer 4 posted
`Ready to merge: no` and failed the check, matching the local result on the same scenario.

A second live-equivalent run against a hand-built five-file diff (three planted defects, one
subtle authorization bug, one clean control file with no defect): Layer 2 flagged all four real
issues, including `IsAuthenticated` on a view documented as admin-only, and raised nothing on the
clean file. This run is also what caught the "drop on verification error" bug described above -
a transient 500 deleted the authorization finding from the verdict on the first attempt; a
clean re-run kept it, isolating the API hiccup as the cause rather than the finding itself.

## Not built yet

Path filtering (e.g. skip non-code PRs), re-running only on new commits rather than the whole
diff each time, and a larger fixture set with known-correct verdicts (`fixtures/` currently has
one scenario) to regression-test `judge.py`/`verify.py`/`gate.py` against when the prompts
change - `eval_verify.py` covers `verify.py`; `judge.py` and `gate.py` have no equivalent yet.
