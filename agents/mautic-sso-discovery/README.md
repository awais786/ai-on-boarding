# mautic-sso-discovery

Claude Agent SDK program for [issue #82](https://github.com/awais786/ai-on-boarding/issues/82):
investigates a target codebase's current authentication against the fixed
Moneta SSO contract (bundled in `context/`), and writes a Markdown discovery
report + integration plan.

Safety properties of the `discover` session:
- The clone is made unwritable (`chmod`) before the session starts.
- Its tool availability is restricted to `Read`/`Grep`/`Glob` via
  `ClaudeAgentOptions.tools` — a real capability restriction, not just an
  auto-approve list — so it has no way to reach `Bash`/`Write`/`Edit` or
  anything else.
- `setting_sources=[]` means it never inherits the operator's own Claude
  settings (e.g. any MCP servers configured on the machine running it).
- A `PreToolUse` hook denies `Read` until at least one `Grep`/`Glob` has
  actually succeeded in that session — enforcing "search before you read"
  in code, not just as a prompt instruction.

## Setup

```bash
cd agents/mautic-sso-discovery
python3 -m venv .venv && source .venv/bin/activate
pip install -e . -r requirements.txt
```

Requires `ANTHROPIC_API_KEY` in the environment (or a `.env` file next to
this README, for local dev only — never committed).

## Usage

**Phase 1 — discovery (writes a local report, touches nothing on GitHub):**

```bash
python -m mautic_sso_discovery discover \
  --target-repo https://github.com/pressingly/mautic \
  --out ./mautic-discovery-report.md
```

Read the report. Only once you're satisfied with it, run phase 2.

**Preview the draft first — no `BOARD_TOKEN` needed, creates nothing:**

```bash
python -m mautic_sso_discovery propose-issues \
  --report ./mautic-discovery-report.md \
  --github-repo awais786/ai-on-boarding \
  --dry-run
```

**Phase 2 — propose issues for real (requires `BOARD_TOKEN`, a GitHub PAT
with repo write access; creates real issues):**

```bash
python -m mautic_sso_discovery propose-issues \
  --report ./mautic-discovery-report.md \
  --github-repo awais786/ai-on-boarding
```

## Choosing a model

Both subcommands default to `claude-sonnet-5`. Override it per-run with
`--model`, or set a persistent default via `MAUTIC_DISCOVERY_MODEL` (env
var, or in `.env`) — `--model` always wins if both are set. See
`python -m mautic_sso_discovery discover --help` for the current list of
valid values (kept there, not duplicated here, so there's one place to
update as models change).

## Tests

```bash
pytest -v
```

All tests fake the Agent SDK's `query()` and GitHub's transport — no
`ANTHROPIC_API_KEY` or `BOARD_TOKEN` needed to run the suite.
