# mautic-sso-discovery

Claude Agent SDK program for [issue #82](https://github.com/awais786/ai-on-boarding/issues/82):
investigates a target codebase's current authentication against the fixed
Moneta SSO contract (bundled in `context/`), and writes a Markdown discovery
report + integration plan. Never modifies the target repo — the clone is
made unwritable before the agent session starts, and the session is never
granted a Write/Edit/Bash tool.

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

**Phase 2 — propose issues (requires `BOARD_TOKEN`, a GitHub PAT with repo
write access; creates real issues):**

```bash
python -m mautic_sso_discovery propose-issues \
  --report ./mautic-discovery-report.md \
  --github-repo awais786/ai-on-boarding
```

## Choosing a model

Both subcommands default to `claude-sonnet-5`. Override it per-run with
`--model`, or set a persistent default via `MAUTIC_DISCOVERY_MODEL` (env
var, or in `.env`) — `--model` always wins if both are set. Valid values
as of this writing:

```
claude-opus-5
claude-sonnet-5              (default)
claude-fable-5-1
claude-haiku-4-5-20251001    (cheapest — good for a low-cost trial run)
```

```bash
python -m mautic_sso_discovery discover \
  --target-repo https://github.com/pressingly/mautic \
  --out ./mautic-discovery-report.md \
  --model claude-haiku-4-5-20251001
```

## Tests

```bash
pytest -v
```

All tests fake the Agent SDK's `query()` and GitHub's transport — no
`ANTHROPIC_API_KEY` or `BOARD_TOKEN` needed to run the suite.
