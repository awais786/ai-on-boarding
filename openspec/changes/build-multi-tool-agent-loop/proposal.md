## Why

The repo currently only demonstrates spec-driven development for a Django REST auth API. There is
no worked example of a Claude tool-use agentic loop — a separate, common pattern (an LLM choosing
between multiple tools, executing them, and continuing until it has a final answer) that is useful
to demonstrate independently of the Django project. This change adds that as a standalone example.

## What Changes

- New standalone Python package at the repo root (`agent_loop/`, alongside `sdd_django_demo/`,
  not part of the Django project) implementing a manual agentic loop against the Anthropic Claude
  Messages API.
- Two tools with JSON Schema `input_schema` definitions: `calculator` (evaluates a math
  expression) and `web_search` (returns mock/stub search results — no live network call).
- A tool dispatcher that maps a requested tool name to its implementation and raises/returns a
  clear error for an unrecognized tool name.
- Loop termination driven solely by `response.stop_reason`: continues on `"tool_use"`, returns the
  final text on `"end_turn"`. No natural-language or `content[0].type` checks are used to decide
  completion.
- A `MAX_ITERATIONS = 20` safety cap that stops the loop and logs a warning if reached — a
  guardrail only, never the normal termination path.
- A test demonstrating the full `web_search → calculator → end_turn` lifecycle for the prompt
  "Find France population and calculate 10%.", asserting tool calls, tool inputs, conversation
  history, and final `stop_reason`, without depending on Claude's exact wording.

## Capabilities

### New Capabilities
- `multi-tool-agent-loop`: A Claude Messages API agentic loop that selects between a `calculator`
  and a `web_search` tool, executes the requested tool(s), feeds results back to Claude, and
  terminates normally on `stop_reason == "end_turn"` (with a `MAX_ITERATIONS` safety cap as a
  non-normal fallback).

### Modified Capabilities
(none — this change does not alter the existing signup/signin/password-reset/embargo behaviour)

## Impact

- Adds a new top-level directory `agent_loop/` (module code + tests), independent of the Django
  project (`sdd_django_demo/`) and its `pytest.ini`/venv — this package needs its own dependency on
  the `anthropic` Python SDK and its own way to run its test(s) (documented in `design.md`/`tasks.md`).
- No changes to `sdd_django_demo/`, its models, migrations, or existing API contracts.
- New dependency: the `anthropic` Python SDK (client for the Claude Messages API).
- Requires an `ANTHROPIC_API_KEY` (or equivalent credential) to exercise the loop for real; the
  test suite must not depend on live network calls or a live API key (see design.md).
