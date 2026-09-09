# pr-review-agent

A three-layer automated PR review. Layer 1 is deterministic tooling; Layers 2 and 3 are Python
agents calling the Claude API directly (`anthropic` SDK) - not the Claude Code CLI.

| Layer | What | Model | Where |
|---|---|---|---|
| 1 | Lint the files the PR changed. Mechanical, always right about what it covers. | - | `lint.py` |
| 2 | Judge the diff for architectural fit, convention compliance, correctness/completeness, and blast radius (duplicated logic elsewhere in the repo). Runs Layer 1 itself first; drops any of its own findings that land on the same file/line as a Layer 1 finding - in code, not by prompt instruction. | `claude-sonnet-5` | `judge.py` |
| 3 | Independently re-check every Layer 2 finding's citation and failure scenario before it can block a merge. Drops or downgrades anything that doesn't hold up. | `claude-haiku-4-5-20251001` | `verify.py` |

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
```

All three accept the same target: a PR number, a branch name, or nothing (the working tree's
uncommitted and staged changes). `target.py` resolves it the same way for every layer, so they
never silently disagree about which files or diff make up "the PR".

## How Layer 2 and 3 work

Both are a manual agentic loop (`agent.py`) over `client.messages.create()`: the model gets
read-only tools (`read_file`, `grep`, `list_files` - `tools.py`, confined to the repo root) to
search the codebase, and every request also carries `output_config.format` with a JSON schema
(`schemas.py`) that constrains the model's *final* text answer. Tool-use turns are unaffected -
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

## Not built yet

There is no CI wiring, and no "gate"/verdict step deciding `Ready to merge: yes/no` from Layer
3's output - deliberately deferred until this shape itself is settled.
