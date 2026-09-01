# Traceability: Multi-Tool Claude Agent Loop

One row per requirement in
[`specs/multi-tool-agent-loop/spec.md`](./specs/multi-tool-agent-loop/spec.md) (this change's
delta - to be merged into `openspec/specs/multi-tool-agent-loop/spec.md` on archive). Code paths
are relative to `agent_loop/` (repo root); test paths are relative to the repo root.

| Requirement | Code | Test |
|---|---|---|
| Register a calculator tool | `tools.py:TOOLS` (calculator schema), `tools.py:evaluate_expression`, `tools.py:calculator` | `test_calculator_tool_schema_declares_name_description_and_expression_input`, `test_calculator_evaluates_arithmetic_expression`, `test_calculator_rejects_non_arithmetic_expression_without_raising`, `test_calculator_reports_division_by_zero_as_error_not_exception`, `test_calculator_rejects_expression_that_would_overflow_a_float_conversion`, `test_calculator_rejects_expression_that_would_recurse_too_deeply` |
| Register a web-search tool | `tools.py:TOOLS` (web_search schema), `tools.py:web_search` | `test_web_search_tool_schema_declares_name_description_and_query_input`, `test_web_search_returns_mock_result_for_known_query`, `test_web_search_returns_fallback_for_unmatched_query` |
| Execute a requested tool and return its result | `loop.py:run_agent_loop` (the `stop_reason == "tool_use"` branch, `tools.dispatch` call, and message threading), `tools.py:dispatch` (never raises on malformed input) | `test_loop_executes_tool_use_and_threads_result_back_to_claude`, `test_dispatch_returns_error_result_for_malformed_input_instead_of_raising` |
| Terminate only on end_turn | `loop.py:run_agent_loop` (checks `response.stop_reason`, never `response.content[0].type` or response text) | `test_loop_terminates_only_on_end_turn_not_on_text_content_type` |
| Support multiple sequential tool calls | `loop.py:run_agent_loop` (the `for` loop over `max_iterations`) | `test_loop_supports_multiple_sequential_tool_calls`, `test_multi_step_live_france_population_search_then_calculate` |
| Enforce a maximum iteration safety cap | `loop.py:MAX_ITERATIONS`, `loop.py:run_agent_loop` (post-loop `logger.warning` and `"max_iterations"` return) | `test_loop_enforces_max_iterations_safety_cap_and_logs_warning` |

## Notes

- `test_dispatch_returns_error_result_for_malformed_input_instead_of_raising` is a regression
  test added after `/code-review` round 1 found `tools.dispatch()` calling each tool's handler
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
  `test_loop_emits_terminated_event_for_a_non_end_turn_stop_reason`; `__main__.py`'s
  post-loop check (which duplicated this same warning) was removed since the event stream now
  reports it directly.
- `test_multi_step_live_france_population_search_then_calculate` is the only test that calls the
  real Claude API; it is `pytest.mark.skipif`'d when `ANTHROPIC_API_KEY` is not set, per
  design.md's live-API test strategy. Every other row is covered by an offline test using a
  scripted fake client (`_ScriptedClient` in `tests/test_agent_loop.py`), so the rest of the
  suite runs without credentials or network access.
- Every row has at least one test; every test in `tests/test_agent_loop.py` serves at least one
  row above. No orphans in either direction.
