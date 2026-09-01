## 1. Project scaffolding

- [x] 1.1 Create the `agent_loop/` package at the repo root (sibling to `sdd_django_demo/`) with
  `__init__.py`, and verify `python -c "import agent_loop"` succeeds
- [x] 1.2 Add `anthropic` to a new `agent_loop/requirements.txt`, pinned to the current stable
  release with a comment recording the date resolved, and verify `pip install -r
  agent_loop/requirements.txt` succeeds in a virtual environment

## 2. Tools

- [x] 2.1 In `agent_loop/tools.py`, define the `calculator` tool's JSON schema (`name`,
  `description`, `input_schema` requiring a string `expression`) and implement it using an
  `ast`-based whitelist evaluator (literals, unary +/-, binary `+ - * / %`, parentheses; no
  `**`, no names, no calls), returning an error result instead of raising on invalid input or
  division by zero
- [x] 2.2 In `agent_loop/tools.py`, define the `web_search` tool's JSON schema (`name`,
  `description`, `input_schema` requiring a string `query`) and implement it as a fixed lookup
  table (including a France-population entry) with a generic fallback string for unmatched
  queries
- [x] 2.3 Add a `TOOLS` list (both schemas) and a `dispatch(name, tool_input)` function in
  `agent_loop/tools.py`, and verify by running each tool directly with a sample input from a
  Python shell

## 3. Agentic loop

- [x] 3.1 In `agent_loop/loop.py`, implement `run_agent_loop(client, messages, max_iterations=20)`
  following design.md's control flow: call `client.messages.create(...)` with `tools=TOOLS`;
  on `stop_reason == "tool_use"`, execute every `tool_use` block via `tools.dispatch`, append the
  assistant message and a user message of `tool_result` blocks, and continue; on
  `stop_reason == "end_turn"`, return the joined text content; on any other `stop_reason`, log a
  warning and return the best-effort text
- [x] 3.2 Add the `MAX_ITERATIONS = 20` cap to the loop: stop and log a warning via the standard
  `logging` module if 20 round trips complete without an `end_turn`, and verify by forcing the
  cap with a fake client that always returns `tool_use` and confirming the warning is logged and
  the loop stops instead of looping forever
- [x] 3.3 Add `agent_loop/__main__.py` so the loop can be run by hand as
  `python -m agent_loop "<prompt>"`, printing the running transcript, and verify by running it
  interactively against the live API with the issue's France-population prompt

## 4. Tests (after implementation, from the spec)

- [x] 4.1 List every requirement in `specs/multi-tool-agent-loop/spec.md` and what a test would
  need to assert, working only from the spec
- [x] 4.2 Write `tests/test_agent_loop.py` from that list, covering the calculator and
  web_search tool schemas/behaviour (including the invalid-expression and unmatched-query
  scenarios) without needing a live API call
- [x] 4.3 Write the multi-step acceptance test that sends the France-population prompt to the
  real Claude API (per design.md's live-API test strategy), asserting `web_search` was called,
  `calculator` was called with an expression evaluating to 10% of the stubbed population figure,
  and the loop terminated via `end_turn` rather than the iteration cap; mark it
  `pytest.mark.skipif` when `ANTHROPIC_API_KEY` is not set
- [x] 4.4 Run `pytest agent_loop/ tests/` (with `ANTHROPIC_API_KEY` set) and confirm all tests
  pass, including the live multi-step test
- [x] 4.5 Prove the safety-cap test can actually fail - temporarily remove the `MAX_ITERATIONS`
  check, confirm the forced-loop test fails (or hangs) as expected, then restore it

## 5. Traceability, review, and issue

- [x] 5.1 Build `traceability.md` (in this change's folder, per convention - see
  `openspec/changes/add-embargo/traceability.md`) mapping every requirement in
  `specs/multi-tool-agent-loop/spec.md` to its code and test
- [x] 5.2 Run `/code-review` and address any finding that cites a requirement, a named failing
  test, or a documented convention
- [x] 5.3 Run `/code-review` again (round 2, verify-only) until it returns `Ready to merge: yes`
