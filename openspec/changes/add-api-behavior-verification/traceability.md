# Traceability: API behaviour verification

One row per requirement in
[`specs/api-behavior-verification/spec.md`](./specs/api-behavior-verification/spec.md).
Requirement identity is the requirement's name, matching the convention established by
[`add-user-signup`](../archive/2026-08-19-add-user-signup/traceability.md) (OpenSpec has no
numeric `FR-XXX` scheme).

Code paths are relative to `tooling/api-verification/` unless stated otherwise. All tests live in
`tooling/api-verification/tests/test_verification.py`, run with `.venv/bin/python -m pytest` from
that directory.

| Requirement | Code | Test |
|---|---|---|
| Run automatically on every push to main | `.github/workflows/api-behavior-verification.yml` (`on.push.branches: [main]`, `on.workflow_dispatch`) | `test_the_workflow_starts_on_a_push_to_main`, `test_the_workflow_can_also_be_started_on_demand` |
| Derive endpoint coverage from the OpenAPI description | `run.sh` (`django spectacular`, then `openapi2postmanv2`), `verify/openapi.py:operations`, `verify/build.py:build` | `test_an_operation_added_to_the_description_is_exercised`, `test_an_operation_removed_from_the_description_stops_being_exercised` |
| Account for every address the application routes | `verify/routes.py:routed_addresses`, `verify/completeness.py:unaccounted`, `verify/surfaces.py:load`, `surfaces.yaml` | `test_an_address_in_none_of_the_three_sources_is_reported`, `test_the_current_tree_leaves_no_address_unaccounted_for`, `test_a_declared_surface_absent_from_the_description_is_exercised`, `test_an_exclusion_without_a_reason_is_refused` |
| Take expected behaviour from the promoted specs | `verify/specs.py` (reads `openspec/specs/` only), `verify/library.py:load_file` (refuses an unknown citation), `checks/*.yaml` | `test_a_citation_naming_an_absent_requirement_is_refused`, `test_a_citation_naming_an_absent_scenario_is_refused`, `test_every_check_cites_a_promoted_requirement` |
| Check specified behaviour, not only a successful status | `verify/library.py:ASSERTION_KINDS`, `verify/build.py:_assertion_js`, `checks/*.yaml` | `test_a_refusal_requirement_is_checked_as_the_spec_states_it`, `test_a_response_shape_requirement_is_checked_against_the_body`, `test_a_forbidden_value_is_checked_for_absence`, `test_most_checks_assert_more_than_a_status_code` |
| Express a requirement spanning several requests as an ordered sequence | `verify/library.py:Check.sequence`, `verify/build.py` (`save_as`, `same_as`, `loadSaved`) | `test_responses_required_to_be_indistinguishable_are_compared_with_each_other`, `test_a_later_effect_is_checked_after_the_earlier_request`, `test_the_collection_preserves_sequence_order` |
| Reach a delivered reset code the way a recipient reaches it | `run.sh` (`RESET_SMTP_*` pointed at the catcher), `checks/user-password-reset.yaml` (`{{mailBaseUrl}}` requests and `regex` captures), `verify/build.py:_script_for` | `test_every_reset_code_is_captured_from_the_delivered_message`, `test_the_response_is_still_checked_for_absence_of_the_code` |
| Record requirements that cannot be observed from outside the process | `verify/register.py` (`CATEGORIES`, `load`), `unobservable.yaml`, `verify/coverage.py:gaps` | `test_every_register_entry_names_a_category_and_a_covering_test`, `test_a_register_entry_without_a_covering_test_is_refused`, `test_an_unknown_category_is_refused`, `test_nothing_is_left_unaccounted_between_the_checks_and_the_register`, `test_recording_one_scenario_leaves_its_siblings_still_required` |
| Execute the checks as a Postman collection | `verify/build.py:build` (v2.1 collection), `run.sh` (`newman run --reporters cli,json`) | `test_the_collection_is_a_postman_collection`, `test_every_request_carries_a_test_script`, `test_an_operation_no_check_refers_to_still_gets_a_status_check` |
| Fail the run when observed behaviour contradicts a requirement | `verify/gate.py:failed_assertions`, `verify/gate.py:main` | `test_a_failed_check_cannot_produce_a_passing_run` |
| Evaluate the checks against the specs before a run may pass | `verify/evaluate.py` (`gather`, `PROMPT`, `Findings`), `verify/gate.py:main` (absent findings file) | `test_a_run_without_an_evaluation_does_not_pass`, `test_a_requirement_with_no_check_and_no_register_entry_fails_the_run` |
| Fail the run on an evaluation finding that names a requirement | `verify/gate.py:blocking_findings` | `test_a_finding_naming_an_unrecorded_requirement_fails_the_run`, `test_a_finding_naming_a_recorded_requirement_does_not_fail_the_run`, `test_a_finding_naming_no_requirement_does_not_fail_the_run` |
| Fail rather than pass when the evaluation cannot be performed | `verify/evaluate.py:EvaluationUnavailable`, `verify/evaluate.py:evaluate` (credential check), `verify/evaluate.py:main` (exit 2) | `test_the_evaluation_fails_rather_than_passes_without_its_credential`, `test_the_evaluation_step_exits_non_zero_without_its_credential`, `test_a_finding_always_carries_a_requirement_field` |
| Document where coverage and expected behaviour come from | `README.md` (*Where each part of the answer comes from*, *When does a run fail?*, *When a run fails on a coverage gap*, *Adding an endpoint*), linked from `README.md` and `sdd_django_demo/README.md` | `test_the_readme_states_where_each_part_of_the_answer_comes_from`, `test_the_readme_states_when_a_run_fails`, `test_the_readme_says_what_to_do_when_a_run_fails_on_a_gap` |

## Notes

**Security-sensitive behaviour is asserted directly.** Two properties are asserted head-on rather
than through a success path, per `openspec/config.yaml`:

- The evaluation fails rather than passes when its credential is missing, and writes no findings
  file when it fails - `test_the_evaluation_step_exits_non_zero_without_its_credential` asserts
  both, so a missing secret can never be mistaken for a clean run.
- A reset code is read only from the delivered message, never from an API response, and the check
  asserting the response omits the code remains in place -
  `test_every_reset_code_is_captured_from_the_delivered_message` and
  `test_the_response_is_still_checked_for_absence_of_the_code`.

**One requirement is verified structurally rather than end to end.** *Evaluate the checks against
the specs before a run may pass* covers a step that calls a model. Its evidence gathering, its
output shape, its failure path, and the gate's consumption of its findings are all tested; the
model call itself is not exercised in the test suite, because it needs a credential the repository
does not yet hold and would spend money on every run. The call's surface was verified against the
installed SDK (`messages.parse` accepting `output_format`, `thinking`, and `model`).

**What the checks currently report.** The library is written from the promoted specs, so it
records the API as contradicting four of them today - see
[`design.md`](./design.md) *Migration Plan* step 3. Those failures are the pipeline working, not
defects in it: every failing check either exercises signup or signin, and no check fails for a
reason traceable to this tooling.
