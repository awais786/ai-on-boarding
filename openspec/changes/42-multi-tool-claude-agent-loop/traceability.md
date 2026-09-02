# Traceability: Multi-Tool Claude Agent Loop

One row per requirement in
[`specs/multi-tool-agent-loop/spec.md`](./specs/multi-tool-agent-loop/spec.md) (this change's
delta - to be merged into `openspec/specs/multi-tool-agent-loop/spec.md` on archive). Code and
test paths are relative to the repo root; all code lives in the single `agent_loop.py` file
(see the "Package layout" -> "File layout" note in design.md - originally a package of
`tools.py`/`loop.py`/`__main__.py`, collapsed into one file to match `enhanced_agent_loop.py`'s
shape).

| Requirement | Code | Test |
|---|---|---|
| Register a calculator tool | `agent_loop.py:TOOLS` (calculator schema), `agent_loop.py:evaluate_expression`, `agent_loop.py:calculator` | `test_calculator_tool_schema_declares_name_description_and_expression_input`, `test_calculator_evaluates_arithmetic_expression`, `test_calculator_rejects_non_arithmetic_expression_without_raising`, `test_calculator_reports_division_by_zero_as_error_not_exception`, `test_calculator_rejects_expression_over_the_length_cap_before_it_can_overflow`, `test_calculator_rejects_expression_over_the_length_cap_before_it_can_recurse`, `test_calculator_rejects_expression_that_evaluates_to_a_non_finite_result` |
| Register a web-search tool | `agent_loop.py:TOOLS` (`web_search_20260209` server-tool declaration; no schema, handler, or `dispatch()` branch) | `test_web_search_is_declared_as_a_provider_executed_server_tool`, `test_web_search_has_no_client_side_dispatch_handler`, `test_dispatch_reports_web_search_as_unknown_since_it_has_no_client_handler` |
| Surface server-executed web-search activity without dispatching it | `agent_loop.py:_emit_server_tool_events`, `agent_loop.py:run_agent_loop` (call site, emitted before text so the search precedes the text reporting on it; also handles `stop_reason == "pause_turn"` in the same branch as `tool_use` so a paused response's `tool_use` blocks are still dispatched rather than dropped - see Notes), `agent_loop.py:_print_event` (`server_tool_use`/`web_search_result`/`pause_turn` branches) | `test_loop_surfaces_server_tool_use_and_web_search_result_without_dispatching`, `test_loop_surfaces_a_web_search_error_result`, `test_print_event_renders_server_tool_use_and_web_search_result`, `test_loop_resends_on_pause_turn_instead_of_terminating`, `test_loop_dispatches_tool_use_blocks_present_alongside_pause_turn`, `test_print_event_renders_pause_turn`, `test_multi_step_live_france_population_search_then_calculate` |
| Execute a requested tool and return its result | `agent_loop.py:run_agent_loop` (the `stop_reason == "tool_use"` branch, `agent_loop.dispatch` call, and message threading - client tools only, i.e. `calculator`), `agent_loop.py:dispatch` (never raises on malformed input) | `test_loop_executes_tool_use_and_threads_result_back_to_claude`, `test_dispatch_returns_error_result_for_malformed_input_instead_of_raising` |
| Indicate when multiple tools are requested in a single turn | `agent_loop.py:run_agent_loop` (`batch_index`/`batch_size` on each `tool_use` event), `agent_loop.py:_print_event` (renders the batch position) | `test_loop_annotates_tool_use_events_with_batch_position_when_requested_together`, `test_loop_marks_a_solo_tool_use_event_with_batch_size_one`, `test_print_event_labels_a_batched_tool_use_but_not_a_solo_one` |
| Terminate only on end_turn | `agent_loop.py:run_agent_loop` (checks `response.stop_reason`, never `response.content[0].type` or response text) | `test_loop_terminates_only_on_end_turn_not_on_text_content_type` |
| Support multiple sequential tool calls | `agent_loop.py:run_agent_loop` (the `for` loop over `max_iterations`) | `test_loop_supports_multiple_sequential_tool_calls`, `test_multi_step_live_france_population_search_then_calculate` |
| Enforce a maximum iteration safety cap | `agent_loop.py:MAX_ITERATIONS`, `agent_loop.py:run_agent_loop` (post-loop `logger.warning` and `"max_iterations"` return) | `test_loop_enforces_max_iterations_safety_cap_and_logs_warning` |

## Notes

- `test_dispatch_returns_error_result_for_malformed_input_instead_of_raising` is a regression
  test added after `/code-review` round 1 found `agent_loop.dispatch()` calling each tool's handler
  unguarded: a `tool_use` block missing a required field, or supplying the wrong type, raised a
  raw `KeyError`/`TypeError`/`AttributeError` and crashed the whole loop, instead of the
  `{"error": ...}` result `dispatch()`'s own docstring and design.md both promise. Fix: `dispatch`
  now catches `KeyError`/`TypeError`/`AttributeError` from the handler and returns an error
  result.
- `test_calculator_rejects_expression_that_would_overflow_a_float_conversion` and
  `test_calculator_rejects_expression_that_would_recurse_too_deeply` are regression tests added
  after `/code-review` round 2 found (via direct reproduction) that a syntactically valid but
  huge expression could raise an uncaught `OverflowError` or `RecursionError`, crashing the loop
  instead of returning an error result. Fix: `evaluate_expression()` now rejects expressions over
  a fixed length (200 characters) before evaluating them, and also catches `ArithmeticError`
  (covers `OverflowError`) and `RecursionError` as defense in depth.
- A fresh `/code-review` pass (run after the change was already marked complete) found that
  design.md's Risks/Trade-offs section still called the round-2 length-cap guard "out of scope,"
  contradicting the code it was supposed to describe - a hand-patch that should have updated the
  design instead. Fix: design.md now documents the guard as a Decision, and its Risks section is
  narrowed to the genuine remaining gap (the cap bounds string length, not AST depth or
  magnitude directly). The same review found a short expression under the length cap
  (`"1e400"`) can still overflow float range via Python's own literal parsing, silently
  returning `{"result": inf}` instead of an error; `evaluate_expression()` now also rejects a
  non-finite result, covered by
  `test_calculator_rejects_expression_that_evaluates_to_a_non_finite_result`. The two existing
  length-cap regression tests were renamed and tightened (`test_calculator_rejects_expression_over_the_length_cap_before_it_can_overflow` /
  `..._before_it_can_recurse`) since they were passing via the length cap, not the
  ArithmeticError/RecursionError handlers their old names claimed to cover.
- The same review found `run_agent_loop`'s `on_event` stream emitted `{"type": "end_turn"}` for
  any non-`tool_use` stop_reason, including an anomalous one like `max_tokens` - indistinguishable
  from normal completion to a caller driving off the event stream, even though the returned
  `terminated_via` value was already correct. Fix: a distinct `{"type": "terminated",
  "stop_reason": ...}` event now carries the real stop_reason, covered by
  `test_loop_emits_terminated_event_for_a_non_end_turn_stop_reason`; `agent_loop.py`'s
  post-loop check (which duplicated this same warning) was removed since the event stream now
  reports it directly.
- Requirement "Indicate when multiple tools are requested in a single turn" was added after the
  fact: Claude's response can contain several `tool_use` blocks at once (Anthropic's parallel
  tool use), but the loop dispatched them one at a time with no signal in the output that they'd
  arrived together - indistinguishable from separate turns. Fix: each `tool_use` event now
  carries `batch_index`/`batch_size`, and the CLI prints `tool_use (N of M requested together):`
  when `batch_size > 1`. This does not change dispatch order - tools still run sequentially, per
  the Risks/Trade-offs note in design.md - it only makes the existing grouping observable. A
  follow-up `/code-review` on this addition found `tasks.md` hadn't been updated to record the
  new requirement (fixed - see its section 6) and that no test asserted the actual rendered CLI
  text, only the underlying event data; `test_print_event_labels_a_batched_tool_use_but_not_a_solo_one`
  closes that gap.
- `test_multi_step_live_france_population_search_then_calculate` is the only test that calls the
  real Claude API; it is `pytest.mark.skipif`'d when `ANTHROPIC_API_KEY` is not set, per
  design.md's live-API test strategy. Every other row is covered by an offline test using a
  scripted fake client (`_ScriptedClient` in `tests/test_agent_loop.py`), so the rest of the
  suite runs without credentials or network access.
- Every row has at least one test; every test in `tests/test_agent_loop.py` serves at least one
  row above. No orphans in either direction.
- **PR #43 review change request**: `web_search` was replaced with Anthropic's provider-executed
  server tool (`{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}`), superseding
  the original client-side stub (`_MOCK_SEARCH_RESULTS`, `web_search()`, its `dispatch()` branch,
  and the tests exercising them - all removed). This split the old "Register a web-search tool"
  requirement's behavior: registration stays under that requirement's name (reworded for a server
  tool), while observing the server's `server_tool_use`/`web_search_tool_result` blocks became a
  new requirement, "Surface server-executed web-search activity without dispatching it," since
  those blocks are never executed or fed back by this code - only surfaced via `on_event`, and
  emitted before the response's text so a search always appears in the transcript before the text
  that reports on it. The "Execute a requested tool and return its result" and "Support multiple
  sequential tool calls" requirements were reworded to scope their `tool_use`/`tool_result`
  language to client tools (`calculator`) only, since `web_search` no longer produces a
  `tool_use` block. Two pre-existing batch/print tests that used `"web_search"` as an arbitrary
  example name for a client `tool_use` block were renamed to a fictitious `"translate"` tool, to
  avoid implying web_search can ever appear as a client tool_use block. The live acceptance
  test's calculator-result assertion was widened from an exact-match tolerance around the old
  fixed stub figure (68 million) to a generous plausible band (5.5M-7.5M), and its tool-name
  assertion loosened to tolerate the live model calling calculator more than once, since the
  population figure and call count now come from a real search and a non-deterministic model
  rather than a fixed stub.
- A later `/code-review` pass (run while implementing the separate `enhanced-agent-loop` change,
  which reviews the full working-tree diff and so also covers uncommitted changes here) found
  `run_agent_loop`'s fallback branch treated `stop_reason == "pause_turn"` as terminal - logging
  a warning and returning immediately - when Anthropic's own bundled tool runner
  (`anthropic.lib.tools`, confirmed by inspecting the installed SDK source) treats it as
  resumable: the server paused a long-running turn (plausible now that `web_search` allows up to
  3 real, network-bound searches in one turn) and expects the paused response resent unchanged so
  it can continue. Fix: a dedicated `stop_reason == "pause_turn"` branch appends the assistant
  message and resends within the same iteration budget, rather than falling through to the
  generic terminal branch; covered by `test_loop_resends_on_pause_turn_instead_of_terminating`.
  The same pass found the live acceptance test's calculator-result assertion inspected only the
  *first* `tool_calls` entry named `calculator`, contradicting its own adjacent comment
  tolerating repeated calculator calls - a non-deterministic model making an earlier, unrelated
  calculator call before the real one would fail the assertion on the wrong value. Fix: the
  assertion now checks whether *any* calculator call's computed result falls in the expected
  band.
- The same pass, cross-checked by four independent finder angles, found the `pause_turn` fix
  above only handled the case of a paused response carrying *no* client `tool_use` blocks: the
  branch appended the assistant message and resent, but never scanned for `tool_use` blocks the
  way the `tool_use` branch did, so a hypothetical response combining `pause_turn` with a
  pending client tool call would silently drop that call - never dispatched, no `tool_result`
  ever produced. Fix: `pause_turn` and `tool_use` are now handled by one unified branch (`if
  response.stop_reason in ("tool_use", "pause_turn")`) that always dispatches any `tool_use`
  blocks present, regardless of which of the two stop_reasons triggered it - this also removed a
  duplicated `messages.append({"role": "assistant", ...})` line the two branches used to repeat
  independently (a separate reuse-angle finding). The same review also found
  `agent_loop.py:_print_event` had no branch for the `pause_turn` event type `agent_loop.py` emits, so a
  real pause_turn produced zero CLI transcript output for that step; fixed with a dedicated
  render branch.
