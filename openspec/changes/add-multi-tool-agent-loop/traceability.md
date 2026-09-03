# Traceability: multi-tool agent loop

One row per requirement in
[`specs/multi-tool-agent-loop/spec.md`](./specs/multi-tool-agent-loop/spec.md). Requirement
identity is the requirement's name; this project has no numeric scheme.

Code paths are relative to `agent_loop/`. Tests live in `agent_loop/tests/`, run from the
repository root with `agent_loop/.venv/bin/python -m pytest agent_loop/tests`.

| Requirement | Code | Test |
|---|---|---|
| Offer a calculator tool | `tools.py:calculator`, `tools.py:TOOLS` | `test_the_calculator_is_offered_with_a_description_and_its_input_schema`, `test_an_arithmetic_expression_is_evaluated` |
| Offer a web search tool | `tools.py:web_search`, `tools.py:_STUB_RESULTS`, `tools.py:TOOLS` | `test_the_web_search_is_offered_with_a_description_and_its_input_schema`, `test_a_known_query_returns_its_stub_result`, `test_an_unmatched_query_still_returns_a_result_rather_than_failing`, `test_searching_makes_no_network_request` |
| Let the model choose the tool | `loop.py:run` (sends `tools` but never `tool_choice`), the `description` fields in `tools.py:TOOLS` | `test_the_model_chooses_the_search_then_the_calculation_and_the_run_completes` (live) |
| Execute every requested tool and return its result | `loop.py:run` (the `for request in requests` block), `tools.py:dispatch`, `tools.py:_HANDLERS` | `test_a_result_is_returned_against_the_request_it_answers`, `test_a_tool_that_cannot_run_returns_an_error_to_the_model_and_the_loop_continues`, `test_a_requested_tool_runs_with_the_input_the_model_supplied`, `test_a_tool_that_does_not_exist_reports_an_error_rather_than_raising`, `test_input_a_tool_cannot_use_reports_an_error_rather_than_raising` |
| Thread results back into the conversation | `loop.py:run` (appends `response.content` whole, then all results in one turn) | `test_the_models_response_is_added_to_the_conversation_whole`, `test_every_result_for_one_response_is_returned_in_a_single_turn` |
| Terminate only on the model's reported stop reason | `loop.py:FINISHED`, `loop.py:REQUESTING_A_TOOL`, the stop-reason branch in `loop.py:run` | `test_a_response_that_leads_with_text_but_requests_a_tool_continues_the_loop`, `test_wording_that_sounds_final_does_not_end_the_loop`, `test_the_loop_returns_the_text_when_the_model_reports_it_has_finished`, `test_a_finished_response_with_several_text_blocks_returns_all_of_them` |
| Support several tool calls in sequence | `loop.py:run` (the iteration loop and its accumulating `messages`) | `test_a_value_found_by_one_tool_is_carried_into_the_next_call` |
| Cap the number of iterations for safety | `loop.py:MAX_ITERATIONS`, `loop.py:IterationLimitExceeded`, the `logger.warning` and `raise` after the loop | `test_reaching_the_safety_cap_records_a_warning`, `test_a_capped_run_cannot_be_received_as_though_it_had_finished`, `test_the_cap_is_twenty_iterations_by_default`, `test_a_normal_run_finishes_well_before_the_safety_cap` |
| Report a response the loop cannot act on | `loop.py:UnusableResponse` and its two raise sites in `loop.py:run` | `test_an_unrecognised_stop_reason_is_reported_rather_than_returned` (`max_tokens`, `refusal`, `pause_turn`, `stop_sequence`), `test_a_tool_request_naming_no_tool_is_reported`, `test_no_turn_is_sent_back_when_a_tool_request_names_no_tool` |
| Evaluate expressions without executing arbitrary code | `tools.py:_evaluate`, `tools.py:_BINARY_OPERATORS`, `tools.py:_UNARY_OPERATORS`, `tools.py:_Refused` | `test_an_expression_that_is_not_arithmetic_is_refused` (7 cases), `test_a_refused_expression_is_never_evaluated`, `test_dividing_by_zero_returns_an_error_rather_than_raising`, `test_an_expression_with_no_finite_value_returns_an_error_rather_than_raising`, `test_a_malformed_expression_returns_an_error_rather_than_raising`, `test_an_expression_with_no_real_value_is_refused` (5 cases, incl. a complex intermediate reaching `//` and `%`) |
| Refuse an expression whose result would be too large to compute | `tools.py:_refuse_unbounded_power`, `tools.py:MAX_RESULT_BITS`, the `ast.Pow` check in `tools.py:_evaluate` | `test_a_power_whose_result_would_be_enormous_is_refused_promptly` (3 cases incl. nesting), `test_ordinary_arithmetic_is_unaffected_by_the_bound` (5 cases), `test_a_power_with_a_float_operand_is_left_to_the_finite_check` |
| Demonstrate the complete lifecycle against a live model | `tests/test_live.py`, `__main__.py` (the by-hand transcript), `tests/conftest.py:pytest_terminal_summary`, `tests/conftest.py:REQUIREMENTS_NEEDING_A_LIVE_MODEL` | `test_the_model_chooses_the_search_then_the_calculation_and_the_run_completes` (live), `test_the_run_names_the_unverified_requirements_when_there_is_no_credential`, `test_nothing_is_reported_as_unverified_when_a_credential_is_present`, `test_the_run_does_not_claim_the_rest_was_verified_when_tests_failed`, and the transcript the entry point prints (`tests/test_cli.py`, 6 tests) |

## Notes

**The security-sensitive requirement is asserted directly.** *Evaluate expressions without
executing arbitrary code* is covered by tests that submit input designed to execute code -
`__import__`, `open`, an attribute reach, a comprehension, a lambda - and assert refusal, rather
than being covered incidentally by a test that only ever passes valid arithmetic.
`test_a_refused_expression_is_never_evaluated` additionally proves the refusal happens *before*
evaluation, by asserting that a file the expression would have written does not exist.

**One test was proved able to fail.** The stop-reason branch was replaced with the content-type
check the change request forbids (`response.content[0].type == "text"`). Eight tests went red,
including both that protect *Terminate only on the model's reported stop reason*; the branch was
then restored and the suite returned to green.

**Two requirements need a live model** and are listed in
`tests/conftest.py:REQUIREMENTS_NEEDING_A_LIVE_MODEL`. When `ANTHROPIC_API_KEY` is absent the
suite still passes, and names them as unverified in its summary rather than omitting them
silently.

**Review pass one raised three code findings, all fixed.** A negative base raised to a fractional
power returned a complex number as a successful result, bypassing the finite check - the spec's
refusal scenario was widened to name a non-real result, and the tool now refuses it. The
unverified-requirements summary claimed "everything else was verified" even when tests had
failed, which is the same misreport it exists to prevent; it now reports failures instead. The
entry point asserted that an event without a stop reason carried a tool result, so a `None` stop
reason produced a traceback rather than the intended message; it now branches on the result.

**Review pass two raised one further finding, fixed.** A complex intermediate reaching an
operator with no complex form - `(-8) ** 0.5 // 2` - raised `TypeError` out of the tool instead
of returning an error result, contradicting the same refusal scenario; the final-value guard was
never reached. `TypeError` now returns the refusal, with both `//` and `%` covered by regression
cases, and ordinary integer division and modulo are unaffected.

**A closing pass confirmed that fix: `Ready to merge: yes`.** It verified the cited case returns
an error result, that ordinary `//` and `%` are unchanged across 338 differential cases, and that
the added `except TypeError` can catch nothing but the intended complex-operand family.

**One nit recorded, not acted on.** The `except TypeError` clause does not interpolate the
exception detail, unlike its `(OverflowError, ValueError)` sibling. Nothing else can reach it
today, so it costs no diagnostic now; a future defect inside `_evaluate` raising `TypeError`
would be reported without detail. Recorded under this project's review contract, which makes a
finding blocking only when it cites a requirement, a named failing test, or a documented
convention - this cites none.

## Results

- 68 tests pass with a credential present.
- 67 pass and 1 is skipped without one, with the skipped requirement named in the run's summary.
- `sdd_django_demo` is untouched: its suite still reports 131 passing.
