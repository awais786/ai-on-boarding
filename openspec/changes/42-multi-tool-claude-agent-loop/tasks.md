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

## 6. Indicate when multiple tools are requested together (post-review addition)

- [x] 6.1 Add the "Indicate when multiple tools are requested in a single turn" requirement to
  `specs/multi-tool-agent-loop/spec.md` and the corresponding decision to `design.md`
- [x] 6.2 In `agent_loop/loop.py`, compute `batch_index`/`batch_size` for each `tool_use` block in
  a response and include them on its `tool_use` on_event event
- [x] 6.3 In `agent_loop/__main__.py`, render `tool_use (N of M requested together):` when
  `batch_size > 1`, with unchanged output when `batch_size == 1`
- [x] 6.4 Write tests from that requirement covering both scenarios (two tools requested
  together, one tool requested alone), and update `traceability.md`
- [x] 6.5 Run `/code-review` and address any finding that cites a requirement, a named failing
  test, or a documented convention

## 7. Replace web_search with Anthropic's server-executed tool (PR #43 review change request)

- [x] 7.1 In `agent_loop/tools.py`, remove `_MOCK_SEARCH_RESULTS`, `web_search()`, and its entry
  in `_TOOL_FUNCTIONS`/`dispatch()`; replace the `web_search` entry in `TOOLS` with the server
  tool declaration `{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}`
- [x] 7.2 In `agent_loop/loop.py`, add handling for `server_tool_use` and `web_search_tool_result`
  content block types in the response, distinct from `tool_use` - surface via a new `on_event`
  event type, and do not call `tools.dispatch` or append a `tool_result` for them
- [x] 7.3 Update `agent_loop/__main__.py`'s `_print_event` to render the new
  `server_tool_use`/`web_search_tool_result` event

## 8. Tests for the web_search migration (after implementation, from the spec)

- [x] 8.1 Update `tests/test_agent_loop.py`: remove the `web_search` schema/mock-result/fallback
  tests tied to the old client-tool shape; add tests (scripted client) asserting the new event is
  surfaced without `tools.dispatch` being called for `web_search`
- [x] 8.2 Update the live acceptance test to reflect that `web_search` is now a real
  server-executed search rather than the fixed France-population stub - decide whether the
  existing population/10% assertions still hold against a real result, or need loosening

## 9. Traceability, review, and round-2 fixes

- [x] 9.1 Update `traceability.md` for the requirements touched by sections 7-8
- [x] 9.2 Run `/code-review` and address any finding that cites a requirement, a named failing
  test, or a documented convention
- [x] 9.3 Run `/code-review` again (round 2, verify-only) - this pass ran while implementing the
  separate `enhanced-agent-loop` change (which reviews the full working-tree diff, so it also
  covered these uncommitted files) and surfaced a real gap: `run_agent_loop` treated
  `stop_reason == "pause_turn"` as terminal instead of resumable, plausible now that
  `web_search` allows up to 3 real, network-bound searches in one turn
- [x] 9.4 Fix: unify the `pause_turn` and `tool_use` branches in `agent_loop/loop.py` so a
  paused response's `tool_use` blocks (if any) are still dispatched rather than silently
  dropped, and `__main__.py`'s `_print_event` gets a `pause_turn` render branch (it previously
  had none, so a real pause_turn produced no CLI output for that step); covered by
  `test_loop_resends_on_pause_turn_instead_of_terminating`,
  `test_loop_dispatches_tool_use_blocks_present_alongside_pause_turn`, and
  `test_print_event_renders_pause_turn`
- [x] 9.5 This section (7-9) was also found to violate `openspec/config.yaml`'s "test tasks
  belong in their own section after implementation" rule by embedding test tasks inside the
  implementation section - fixed by splitting section 7 into 7 (implementation), 8 (tests), 9
  (traceability/review), as done above
