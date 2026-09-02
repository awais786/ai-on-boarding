# agent_loop

A worked example of a Claude Messages API agentic tool-use loop, independent of the
`sdd_django_demo/` Django project in this repo. Claude chooses between two tools —
`calculator` and `web_search` (a mock/stub, no live network call) — and the loop keeps
going until the API reports the turn is complete (`stop_reason == "end_turn"`).

See `../openspec/changes/build-multi-tool-agent-loop/specs/multi-tool-agent-loop/spec.md` for the
full behavior contract (moves to `../openspec/specs/multi-tool-agent-loop/spec.md` once this
change is archived).

## Install

`agent_loop/` has its own virtual environment, independent of `sdd_django_demo/`'s:

```bash
python3 -m venv agent_loop/.venv
agent_loop/.venv/bin/pip install -r agent_loop/requirements.txt
```

## Run the loop

Requires a live `ANTHROPIC_API_KEY` in the environment (only the actual loop run needs
this — the tests do not). Put it in a `.env` file at the repo root (gitignored) and load it,
or export it directly:

```bash
export ANTHROPIC_API_KEY=<your key>
agent_loop/.venv/bin/python -m agent_loop.loop "Find France population and calculate 10%."
```

## Run the tests

The tests mock the Anthropic client, so no API key or network access is needed:

```bash
agent_loop/.venv/bin/python -m pytest agent_loop/
```
