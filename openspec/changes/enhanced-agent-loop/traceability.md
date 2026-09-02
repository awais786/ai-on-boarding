# Traceability: Enhanced Agent Loop

One row per requirement in
[`specs/enhanced-agent-loop/spec.md`](./specs/enhanced-agent-loop/spec.md) (this change's
delta - to be merged into `openspec/specs/enhanced-agent-loop/spec.md` on archive). Code and
test paths are relative to the repo root; both live in a single file each
(`enhanced_agent_loop.py`, `tests/test_enhanced_agent_loop.py`) since this is a standalone
script, not a package.

| Requirement | Code | Test |
|---|---|---|
| Provide a real web-search tool via DuckDuckGo | `enhanced_agent_loop.py:web_search` (GET to the Instant Answer API, `AbstractText`/fallback) | `test_web_search_returns_the_abstract_text_when_present`, `test_web_search_returns_fallback_when_abstract_is_empty`, `test_live_france_population_divided_by_1000_completes_with_a_web_search_action` |
| web_search never raises | `enhanced_agent_loop.py:web_search` (a single broad `except Exception` around the request/parse block, not an enumerated tuple - see Notes) | `test_web_search_reports_a_connection_failure_as_an_error_not_an_exception`, `test_web_search_reports_a_timeout_as_an_error_not_an_exception`, `test_web_search_reports_malformed_json_as_an_error_not_an_exception`, `test_web_search_reports_a_non_utf8_response_body_as_an_error_not_an_exception`, `test_web_search_reports_an_unanticipated_exception_as_an_error_not_an_exception` |
| Validate tool arguments at the dispatch boundary | `enhanced_agent_loop.py:validate_args`, `enhanced_agent_loop.py:dispatch` (calls `validate_args` first, short-circuits on a non-`None` result) | `test_dispatch_returns_a_validation_error_for_malformed_input_instead_of_crashing` (8 parametrized cases), `test_dispatch_never_calls_the_real_tool_when_validation_fails`, `test_dispatch_calls_the_real_tool_when_validation_passes` |
| Steer tool ordering with a few-shot example | `enhanced_agent_loop.py:FEW_SHOT_EXAMPLE`, `enhanced_agent_loop.py:run_agent_loop` (prepends it before the real user message) | `test_few_shot_example_precedes_the_real_user_message`, `test_live_ambiguous_request_triggers_web_search_before_calculator` (3 phrasings) |
| Run as a standalone script | `enhanced_agent_loop.py:main`, `_print_event`, `run_agent_loop` (the `ask -> dispatch -> observe -> repeat` loop, `MAX_ITERATIONS` cap) | `test_live_france_population_divided_by_1000_completes_with_a_web_search_action` (end-to-end); loop mechanics covered by `test_loop_executes_tool_use_and_threads_result_back_to_claude`, `test_loop_terminates_only_on_end_turn_not_on_text_content_type`, `test_loop_surfaces_a_validation_error_as_an_action_event_without_crashing`, `test_loop_enforces_max_iterations_safety_cap_and_logs_warning`; the no-args usage-message path was verified by hand (task 1.1), not a permanent test |

## Notes

- Every row has at least one test; every test in `tests/test_enhanced_agent_loop.py` serves at
  least one row above, except `test_calculator_evaluates_arithmetic_expression` and
  `test_calculator_rejects_non_arithmetic_expression_without_raising`, which cover
  `calculator` - not itself a requirement in this delta spec (the review comment's "reject a
  non-string/empty/oversized expr for calculator" is the "Validate tool arguments" requirement
  above; `calculator`'s own arithmetic behavior is out of scope here, since it is a straight copy
  of the already-specified and already-tested `agent_loop/tools.py:calculator`). Kept as
  lightweight sanity checks that the copy behaves the same, not spec-driven requirement tests.
- `test_live_france_population_divided_by_1000_completes_with_a_web_search_action` and
  `test_live_ambiguous_request_triggers_web_search_before_calculator` are `pytest.mark.skipif`'d
  when `ANTHROPIC_API_KEY` is not set, per `agent_loop/`'s existing live-test pattern. **These
  were not run in this environment** - no key was available - so the "Provide a real web-search
  tool," "Steer tool ordering," and "Run as a standalone script" rows are verified offline plus
  by hand (direct calls to `web_search`/`calculator`/`dispatch`, a scripted-client run showing
  few-shot ordering, a forced `MAX_ITERATIONS` cap), but not yet by an actual live Claude run.
  Run `pytest tests/test_enhanced_agent_loop.py` with `ANTHROPIC_API_KEY` set before treating
  this change as fully verified.
- The safety-cap test's ability to fail was proven directly (task 4.6): temporarily changing
  `for _ in range(max_iterations):` to `for _ in range(max_iterations * 1000):` made
  `test_loop_enforces_max_iterations_safety_cap_and_logs_warning` fail with
  `IndexError: pop from empty list` (the scripted client's fixed 5-response list ran dry once the
  cap stopped limiting iterations to 5), confirming the test is not vacuously passing. The file
  was restored and diffed byte-for-byte against the pre-edit version afterward.
- A `/code-review` pass found `web_search`'s original `except (URLError, TimeoutError,
  JSONDecodeError)` tuple missed real failure modes the spec's "for any failure mode" language
  requires covering - `json.loads` raising `UnicodeDecodeError` on a non-UTF-8 response body, or
  a socket read raising `ConnectionResetError`/`http.client.IncompleteRead`, neither of which is
  a subclass of the three caught types. Any of these would have propagated uncaught past
  `web_search`, past `dispatch`'s narrower catch tuple (which doesn't cover them either), and
  crashed the whole loop. Fix: the request/parse block now catches `Exception` broadly - this one
  boundary is exactly what the original review comment asked to be wrapped "for any failure,"
  so a deliberately wide catch is justified here rather than elsewhere in the codebase; covered
  by `test_web_search_reports_a_non_utf8_response_body_as_an_error_not_an_exception` and
  `test_web_search_reports_an_unanticipated_exception_as_an_error_not_an_exception`.
- `dispatch`'s own `except (KeyError, TypeError, AttributeError)` guard (mirroring
  `agent_loop/tools.py:dispatch`) is defense in depth behind `validate_args`, not itself required
  by the spec - `validate_args` is what makes every case in
  `test_dispatch_returns_a_validation_error_for_malformed_input_instead_of_crashing` pass, since
  it rejects each one before the real tool function is ever called.
