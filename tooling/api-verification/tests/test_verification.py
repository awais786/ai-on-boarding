"""Tests for the API behaviour verification, written from its spec.

Working only from `specs/api-behavior-verification/spec.md`, each requirement and
what a test has to assert for it:

 1. Run automatically on every push to main - the workflow triggers on a push to
    `main` and can also be started on demand.
 2. Derive endpoint coverage from the OpenAPI description - an operation added to
    the description is exercised with no other change; one removed stops being.
 3. Account for every address the application routes - a routed address in none
    of the three sources is reported; a declared one is exercised; an exclusion
    states a reason.
 4. Take expected behaviour from the promoted specs - a citation naming a
    requirement or scenario absent from the promoted spec is refused, and every
    citation in the library resolves.
 5. Check specified behaviour, not only a successful status - refusals, response
    bodies and forbidden values are asserted, not just status codes.
 6. Express a requirement spanning several requests as an ordered sequence -
    sequences of more than one request exist, order is preserved, and responses
    required to be indistinguishable are compared with each other.
 7. Reach a delivered reset code the way a recipient reaches it - every code is
    captured from the mail catcher, never from an API response, and the check
    that the response omits the code is still present.
 8. Record requirements that cannot be observed - every entry resolves, names a
    category and a covering test; a recorded entry is not a gap; recording one
    scenario does not excuse its siblings.
 9. Execute the checks as a Postman collection - the built collection is v2.1 and
    every request carries a test script, so nothing executes unchecked.
10. Fail the run when observed behaviour contradicts a requirement - a report
    holding a failed check cannot produce a passing run.
11. Evaluate the checks against the specs before a run may pass - a run with no
    findings file does not pass.
12. Fail the run on an evaluation finding that names a requirement - blocking
    when unrecorded, not blocking when recorded, not blocking when unnamed.
13. Fail rather than pass when the evaluation cannot be performed - a missing
    credential fails and says what is missing.
14. Document where coverage and expected behaviour come from - the README states
    each source's responsibility and the conditions under which a run fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from verify import (  # noqa: E402
    build,
    completeness,
    coverage,
    evaluate,
    gate,
    library,
    openapi,
    register,
    specs,
    surfaces,
)

SPECS = REPO / "openspec" / "specs"
WORKFLOW = REPO / ".github" / "workflows" / "api-behavior-verification.yml"


SCHEMA = HERE / "build" / "schema.yaml"


@pytest.fixture(scope="session", autouse=True)
def generated_schema():
    """Generate the OpenAPI description if this checkout has not got one.

    The description is derived from the Django code, so the suite can produce it
    rather than depending on a previous run having left one behind. Without this
    the tests pass in a working directory that has run the chain and fail in a
    fresh clone - which is the checkout a reviewer and CI both start from.
    """
    if SCHEMA.exists():
        return SCHEMA
    SCHEMA.parent.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "sdd_django_demo"), str(HERE)])
    env["DJANGO_SETTINGS_MODULE"] = "verify.run_settings"
    subprocess.run(
        [sys.executable, "-m", "django", "spectacular", "--file", str(SCHEMA)],
        cwd=HERE, env=env, check=True, capture_output=True,
    )
    return SCHEMA


@pytest.fixture(scope="module")
def capabilities():
    return specs.load(SPECS)


@pytest.fixture(scope="module")
def checks(capabilities):
    return library.load(HERE / "checks", capabilities)


@pytest.fixture(scope="module")
def entries(capabilities):
    return register.load(HERE / "unobservable.yaml", capabilities)


@pytest.fixture(scope="module")
def declared():
    return surfaces.load(HERE / "surfaces.yaml")


@pytest.fixture(scope="module")
def collection():
    return build.build(HERE / "build" / "schema.yaml", HERE / "checks", HERE / "surfaces.yaml", SPECS)


def _requests(collection):
    for folder in collection["item"]:
        for item in folder["item"]:
            yield folder, item


# 1. Run automatically on every push to main


def test_the_workflow_starts_on_a_push_to_main():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert triggers["push"]["branches"] == ["main"]


def test_the_workflow_can_also_be_started_on_demand():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    triggers = workflow[True] if True in workflow else workflow["on"]
    assert "workflow_dispatch" in triggers


# 2. Derive endpoint coverage from the OpenAPI description


def test_an_operation_added_to_the_description_is_exercised(tmp_path):
    schema = yaml.safe_load((HERE / "build" / "schema.yaml").read_text())
    schema["paths"]["/api/invented/"] = {
        "get": {"operationId": "invented_retrieve", "responses": {"200": {"description": "ok"}}}
    }
    path = tmp_path / "schema.yaml"
    path.write_text(yaml.safe_dump(schema))
    built = build.build(path, HERE / "checks", HERE / "surfaces.yaml", SPECS)
    urls = [item["request"]["url"] for _, item in _requests(built)]
    assert any("/api/invented/" in url for url in urls)


def test_an_operation_removed_from_the_description_stops_being_exercised(tmp_path):
    schema = yaml.safe_load((HERE / "build" / "schema.yaml").read_text())
    del schema["paths"]["/api/health/"]
    path = tmp_path / "schema.yaml"
    path.write_text(yaml.safe_dump(schema))
    built = build.build(path, HERE / "checks", HERE / "surfaces.yaml", SPECS)
    urls = [item["request"]["url"] for _, item in _requests(built)]
    assert not any("/api/health/" in url for url in urls)


# 3. Account for every address the application routes


def test_an_address_in_none_of_the_three_sources_is_reported(declared):
    described = openapi.operations(openapi.load(HERE / "build" / "schema.yaml"))
    routed = [{"path": "/an-unclassified-page/", "methods": ["GET"]}]
    assert completeness.unaccounted(routed, described, declared) == ["GET /an-unclassified-page/"]


def test_the_current_tree_leaves_no_address_unaccounted_for(declared):
    from verify import routes

    described = openapi.operations(openapi.load(HERE / "build" / "schema.yaml"))
    assert completeness.unaccounted(routes.routed_addresses(), described, declared) == []


def test_a_declared_surface_absent_from_the_description_is_exercised(collection, declared):
    for entry in declared.declared:
        stem = entry.path.split("<")[0]
        for method in entry.methods:
            assert any(
                item["request"]["method"] == method and stem in item["request"]["url"]
                for _, item in _requests(collection)
            ), f"{method} {entry.path} is declared but absent from the collection"


def test_an_exclusion_without_a_reason_is_refused(tmp_path):
    path = tmp_path / "surfaces.yaml"
    path.write_text("excluded:\n  - path: /x/\n    reason: '  '\n")
    with pytest.raises(surfaces.SurfacesError):
        surfaces.load(path)


# 4. Take expected behaviour from the promoted specs


def test_a_citation_naming_an_absent_requirement_is_refused(capabilities, tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "capability: user-signin\nchecks:\n  - requirement: Not a real requirement\n"
        "    sequence:\n      - {name: x, operation: signin_create}\n"
    )
    with pytest.raises(library.LibraryError):
        library.load_file(path, capabilities)


def test_a_citation_naming_an_absent_scenario_is_refused(capabilities, tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "capability: user-signin\nchecks:\n  - requirement: Return HTTP 401 on rejection\n"
        "    scenario: Not a real scenario\n"
        "    sequence:\n      - {name: x, operation: signin_create}\n"
    )
    with pytest.raises(library.LibraryError):
        library.load_file(path, capabilities)


def test_every_check_cites_a_promoted_requirement(checks, capabilities):
    for check in checks:
        requirement = capabilities[check.capability].requirement(check.requirement)
        assert requirement is not None, check.citation
        if check.scenario:
            assert requirement.scenario(check.scenario) is not None, check.citation


# 5. Check specified behaviour, not only a successful status


def test_a_refusal_requirement_is_checked_as_the_spec_states_it(checks):
    check = next(c for c in checks if c.requirement == "Reject a missing email"
                 and c.capability == "user-signup")
    kinds = {k for r in check.sequence for a in r.assertions for k in a}
    assert "status" in kinds and "json_has" in kinds


def test_a_response_shape_requirement_is_checked_against_the_body(checks):
    check = next(c for c in checks if c.requirement == "Signal success with the created account's email")
    kinds = {k for r in check.sequence for a in r.assertions for k in a}
    assert "json_only_keys" in kinds, "the spec allows only the email field; a status check cannot see that"


def test_a_forbidden_value_is_checked_for_absence(checks):
    for capability in ("user-signup", "user-signin"):
        check = next(c for c in checks if c.capability == capability
                     and c.requirement == "Never return the password")
        kinds = {k for r in check.sequence for a in r.assertions for k in a}
        assert "body_excludes" in kinds


def test_most_checks_assert_more_than_a_status_code(checks):
    beyond = [c for c in checks
              if {k for r in c.sequence for a in r.assertions for k in a} - {"status"}]
    assert len(beyond) > len(checks) / 2


# 6. Express a requirement spanning several requests as an ordered sequence


def test_responses_required_to_be_indistinguishable_are_compared_with_each_other(checks):
    """Selected by requirement, not by scenario name: the requirement is what the
    behaviour hangs on, and a spec may reword a scenario without changing it."""
    candidates = [c for c in checks if c.requirement == "Reject all failure modes identically"]
    assert candidates, "no check covers the requirement that refusals be indistinguishable"
    for check in candidates:
        assert len(check.sequence) > 1, check.citation
        assert any("same_as" in a for r in check.sequence for a in r.assertions), check.citation
        assert any(r.save_as for r in check.sequence), check.citation


def test_a_later_effect_is_checked_after_the_earlier_request(checks):
    check = next(c for c in checks if c.requirement == "Complete a reset with a valid code"
                 and c.scenario == "The old password stops working")
    names = [r.name for r in check.sequence]
    assert names.index("complete the reset") < len(names) - 1


def test_the_collection_preserves_sequence_order(collection, checks):
    by_citation = {c.citation: c for c in checks}
    for folder in collection["item"]:
        check = by_citation.get(folder["name"])
        if check is None:
            continue
        built = [i["name"] for i in folder["item"] if not i["name"].startswith("fetch the form")]
        assert built == [r.name for r in check.sequence]


# 7. Reach a delivered reset code the way a recipient reaches it


def test_every_reset_code_is_captured_from_the_delivered_message(collection):
    captures = 0
    for _, item in _requests(collection):
        script = "\n".join(item["event"][0]["script"]["exec"])
        if "reset-password/([" in script:
            captures += 1
            assert "mailBaseUrl" in item["request"]["url"], item["name"]
    assert captures > 0


def test_the_response_is_still_checked_for_absence_of_the_code(checks):
    check = next(c for c in checks if c.requirement == "Never return the reset code in a response")
    assertions = [a for r in check.sequence for a in r.assertions]
    assert any("saved_excludes" in a for a in assertions)


# 8. Record requirements that cannot be observed from outside the process


def test_every_register_entry_names_a_category_and_a_covering_test(entries):
    for entry in entries:
        assert entry.category in register.CATEGORIES
        assert entry.reason.strip()
        assert entry.covered_by.strip()


def test_a_register_entry_without_a_covering_test_is_refused(capabilities, tmp_path):
    path = tmp_path / "r.yaml"
    path.write_text(
        "entries:\n  - capability: user-signin\n"
        "    requirement: Return HTTP 401 on rejection\n"
        "    category: time-bound\n    reason: because\n"
    )
    with pytest.raises(register.RegisterError):
        register.load(path, capabilities)


def test_an_unknown_category_is_refused(capabilities, tmp_path):
    path = tmp_path / "r.yaml"
    path.write_text(
        "entries:\n  - capability: user-signin\n"
        "    requirement: Return HTTP 401 on rejection\n"
        "    category: inconvenient\n    reason: because\n    covered_by: somewhere\n"
    )
    with pytest.raises(register.RegisterError):
        register.load(path, capabilities)


def test_nothing_is_left_unaccounted_between_the_checks_and_the_register(
    capabilities, checks, entries
):
    assert coverage.gaps(capabilities, checks, entries) == []


def test_recording_one_scenario_leaves_its_siblings_still_required(capabilities, checks):
    """A partial entry must not suppress the sibling scenarios of its requirement."""
    partial = register.Entry(
        capability="user-signin",
        requirement="Lock an email out after repeated failures",
        scenario="Lockout expires",
        category="time-bound",
        reason="r",
        covered_by="t",
        partial=True,
    )
    without_sibling = [c for c in checks
                       if not (c.requirement == "Lock an email out after repeated failures")]
    found = coverage.gaps(capabilities, without_sibling, [partial])
    assert any(g.scenario == "Third failure triggers lockout" for g in found)


# 9. Execute the checks as a Postman collection


def test_the_collection_is_a_postman_collection(collection):
    assert "v2.1.0" in collection["info"]["schema"]


def test_every_request_carries_a_test_script(collection):
    for folder, item in _requests(collection):
        exec_lines = item["event"][0]["script"]["exec"]
        assert exec_lines, f"{folder['name']} / {item['name']} executes with nothing checked"


def test_an_operation_no_check_refers_to_still_gets_a_status_check(collection):
    folder = next(f for f in collection["item"] if f["name"] == "Operations no check refers to")
    assert folder["item"]
    for item in folder["item"]:
        assert "pm.response.code" in "\n".join(item["event"][0]["script"]["exec"])


# 10-12. The gate


def _report(failed: bool) -> dict:
    assertion = {"assertion": "user-signup: Reject a missing email / Email omitted :: status"}
    if failed:
        assertion["error"] = {"message": "expected 400 but got 200"}
    return {"run": {"executions": [{"assertions": [assertion]}]}}


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


def test_a_failed_check_cannot_produce_a_passing_run(tmp_path):
    report = _write(tmp_path, "report.json", _report(failed=True))
    findings = _write(tmp_path, "findings.json", {"findings": []})
    assert gate.main(
        ["--skip-completeness", "--report", str(report), "--findings", str(findings)]
    ) == 1


def test_a_run_without_an_evaluation_does_not_pass(tmp_path):
    report = _write(tmp_path, "report.json", _report(failed=False))
    assert gate.main(
        ["--skip-completeness", "--report", str(report),
         "--findings", str(tmp_path / "absent.json")]
    ) == 1


def test_a_finding_naming_an_unrecorded_requirement_fails_the_run(tmp_path):
    report = _write(tmp_path, "report.json", _report(failed=False))
    findings = _write(tmp_path, "findings.json", {"findings": [
        {"kind": "missing_check", "capability": "user-signup",
         "requirement": "Reject a missing email", "scenario": "Email omitted",
         "summary": "s", "detail": "d"}]})
    assert gate.main(
        ["--skip-completeness", "--report", str(report), "--findings", str(findings)]
    ) == 1


def test_a_finding_naming_a_recorded_requirement_does_not_fail_the_run(tmp_path):
    report = _write(tmp_path, "report.json", _report(failed=False))
    findings = _write(tmp_path, "findings.json", {"findings": [
        {"kind": "missing_check", "capability": "user-signin",
         "requirement": "Lock an email out after repeated failures",
         "scenario": "Lockout expires", "summary": "s", "detail": "d"}]})
    assert gate.main(
        ["--skip-completeness", "--report", str(report), "--findings", str(findings)]
    ) == 0


def test_a_finding_naming_no_requirement_does_not_fail_the_run(tmp_path):
    report = _write(tmp_path, "report.json", _report(failed=False))
    findings = _write(tmp_path, "findings.json", {"findings": [
        {"kind": "status_only", "capability": "", "requirement": "", "scenario": "",
         "summary": "health is checked only for a status code", "detail": "d"}]})
    assert gate.main(
        ["--skip-completeness", "--report", str(report), "--findings", str(findings)]
    ) == 0


# 13. Fail rather than pass when the evaluation cannot be performed


def test_the_evaluation_fails_rather_than_passes_without_its_credential(monkeypatch):
    monkeypatch.delenv(evaluate.CREDENTIAL, raising=False)
    with pytest.raises(evaluate.EvaluationUnavailable) as raised:
        evaluate.evaluate({"promoted_requirements": []})
    assert evaluate.CREDENTIAL in str(raised.value)


def test_the_evaluation_step_exits_non_zero_without_its_credential(monkeypatch, tmp_path):
    monkeypatch.delenv(evaluate.CREDENTIAL, raising=False)
    status = evaluate.main(
        ["--report", str(tmp_path / "absent.json"), "--out", str(tmp_path / "findings.json")]
    )
    assert status != 0
    assert not (tmp_path / "findings.json").exists(), "no findings may be written without a run"


def test_a_finding_always_carries_a_requirement_field():
    finding = evaluate.Finding(kind="status_only", summary="s", detail="d")
    assert finding.requirement == ""


# 14. Document where coverage and expected behaviour come from


def test_the_readme_states_where_each_part_of_the_answer_comes_from():
    text = (HERE / "README.md").read_text()
    for phrase in ("Which endpoints exist?", "How must they behave?",
                   "OpenAPI description", "openspec/specs/"):
        assert phrase in text


def test_the_readme_states_when_a_run_fails():
    text = (HERE / "README.md").read_text()
    assert "When does a run fail?" in text
    for phrase in ("coverage incomplete", "any check failed", "the evaluation could not run"):
        assert phrase in text


def test_the_readme_says_what_to_do_when_a_run_fails_on_a_gap():
    text = (HERE / "README.md").read_text()
    assert "When a run fails on a coverage gap" in text
    assert "Write the check" in text and "Record it as unobservable" in text


def test_a_requirement_with_no_check_and_no_register_entry_fails_the_run(tmp_path):
    """Deterministic, so an unclassified requirement is reported whether or not
    the evaluation runs."""
    thin = tmp_path / "checks"
    thin.mkdir()
    (thin / "user-signup.yaml").write_text("capability: user-signup\nchecks: []\n")
    report = _write(tmp_path, "report.json", _report(failed=False))
    findings = _write(tmp_path, "findings.json", {"findings": []})
    assert gate.main(
        ["--skip-completeness", "--report", str(report), "--findings", str(findings),
         "--checks", str(thin)]
    ) == 1


# Regressions fixed after review. Each asserts the behaviour the spec requires,
# not the shape of the fix.


def test_a_request_that_never_completed_cannot_pass_as_a_held_check(tmp_path):
    """Requirement: Execute the checks as a Postman collection / Every check
    produces a recorded outcome. A request that errors records no assertions."""
    report = _write(tmp_path, "report.json", {"run": {"executions": [
        {"item": {"name": "a message was delivered to that address"},
         "requestError": "connect ECONNREFUSED"}]}})
    findings = _write(tmp_path, "findings.json", {"findings": []})
    assert gate.main(
        ["--skip-completeness", "--report", str(report), "--findings", str(findings)]
    ) == 1


def test_a_test_script_that_threw_cannot_pass_as_a_held_check(tmp_path):
    report = _write(tmp_path, "report.json", {"run": {"executions": [
        {"item": {"name": "read the delivered code"},
         "testScript": [{"error": {"message": "Unexpected token < in JSON"}}]}]}})
    findings = _write(tmp_path, "findings.json", {"findings": []})
    assert gate.main(
        ["--skip-completeness", "--report", str(report), "--findings", str(findings)]
    ) == 1


def test_a_skipped_check_cannot_pass_as_a_held_check(tmp_path):
    report = _write(tmp_path, "report.json", {"run": {"executions": [
        {"item": {"name": "x"},
         "assertions": [{"assertion": "cap: Req / Scen :: status", "skipped": True}]}]}})
    findings = _write(tmp_path, "findings.json", {"findings": []})
    assert gate.main(
        ["--skip-completeness", "--report", str(report), "--findings", str(findings)]
    ) == 1


def test_a_run_level_error_cannot_pass(tmp_path):
    report = _write(tmp_path, "report.json", {"run": {"error": "collection could not be read",
                                                      "executions": []}})
    findings = _write(tmp_path, "findings.json", {"findings": []})
    assert gate.main(
        ["--skip-completeness", "--report", str(report), "--findings", str(findings)]
    ) == 1


def test_a_setup_request_asserting_nothing_is_not_a_failure(tmp_path):
    """Sequences carry capture and setup steps by design; those must not be read
    as checks that failed to run."""
    report = _write(tmp_path, "report.json", {"run": {"executions": [
        {"item": {"name": "find the delivered message"}},
        {"item": {"name": "x"}, "assertions": [{"assertion": "cap: Req / Scen :: status"}]}]}})
    findings = _write(tmp_path, "findings.json", {"findings": []})
    assert gate.main(
        ["--skip-completeness", "--report", str(report), "--findings", str(findings)]
    ) == 0


def test_an_assertion_naming_two_kinds_is_refused(capabilities, tmp_path):
    """Only one kind could be emitted, so the other would go unchecked."""
    path = tmp_path / "c.yaml"
    path.write_text(
        "capability: user-signin\nchecks:\n  - requirement: Return HTTP 401 on rejection\n"
        "    sequence:\n      - name: x\n        operation: signin_create\n"
        "        assert:\n          - {status: 401, json_has: email}\n"
    )
    with pytest.raises(library.LibraryError):
        library.load_file(path, capabilities)


def test_a_query_string_reaches_the_built_request(capabilities, tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "capability: user-signin\nchecks:\n  - requirement: Return HTTP 401 on rejection\n"
        "    sequence:\n      - name: x\n        operation: signin_create\n"
        "        query: {probe: '1'}\n"
    )
    check = library.load_file(path, capabilities)[0]
    described = {o["operation_id"]: o for o in
                 openapi.operations(openapi.load(HERE / "build" / "schema.yaml"))}
    item = build._item(check.sequence[0], check.citation, described)
    assert "probe=1" in item["request"]["url"]


def test_a_requirement_with_no_scenarios_is_still_classified(capabilities):
    """The one shape the scenario loop would never reach."""
    bare = specs.Requirement(capability="user-signup", name="A bare requirement",
                             text="t", scenarios=())
    only = {"user-signup": specs.Capability("user-signup", (bare,))}
    assert coverage.gaps(only, [], []) == [coverage.Gap("user-signup", "A bare requirement", None)]


def test_a_plain_function_view_has_all_its_methods_demanded():
    """Django routes every method to a function view; reporting only GET would
    let the others past the completeness check unaccounted for."""
    from verify import routes

    assert routes._methods_for(lambda request: None) == [
        "DELETE", "GET", "PATCH", "POST", "PUT"
    ]


def test_a_templated_operation_with_no_check_is_refused_at_build(tmp_path):
    """A default status check cannot invent a path parameter."""
    schema = yaml.safe_load((HERE / "build" / "schema.yaml").read_text())
    schema["paths"]["/api/thing/{id}/"] = {
        "get": {"operationId": "thing_retrieve", "responses": {"200": {"description": "ok"}}}
    }
    path = tmp_path / "schema.yaml"
    path.write_text(yaml.safe_dump(schema))
    with pytest.raises(ValueError, match="path parameter"):
        build.build(path, HERE / "checks", HERE / "surfaces.yaml", SPECS)


def test_the_readmes_do_not_claim_the_run_blocks_a_merge():
    """The workflow triggers on push to main; it reports after a merge lands."""
    for name in ("README.md", "sdd_django_demo/README.md"):
        text = (REPO / name).read_text()
        assert "fails a merge" not in text, name
        assert "run on every merge" not in text, name


def test_every_request_carries_a_unique_id(collection):
    ids = [item["id"] for _, item in _requests(collection)]
    assert len(ids) == len(set(ids))
    assert all(ids)


def test_an_errored_request_names_its_own_check_not_another(collection, tmp_path):
    """Requirement: Fail the run when observed behaviour contradicts a
    requirement / Scenario: A contradicted requirement fails the run - the run
    must name the requirement THAT check verifies. Request names repeat across
    checks, so a name-keyed lookup files the failure under the wrong one."""
    shared = "create the account"
    owners = [f["name"] for f in collection["item"]
              if any(i["name"] == shared for i in f["item"])]
    assert len(owners) > 1, "this test needs a request name used by more than one check"

    # Pick a check that is NOT the one a name-keyed map would resolve to.
    by_name_would_give = owners[-1]
    target = owners[0]
    assert target != by_name_would_give
    target_id = next(i["id"] for f in collection["item"] if f["name"] == target
                     for i in f["item"] if i["name"] == shared)

    collection_path = tmp_path / "collection.json"
    collection_path.write_text(json.dumps(collection))
    report_path = _write(tmp_path, "report.json", {"run": {"executions": [
        {"item": {"id": target_id, "name": shared},
         "requestError": "connect ECONNREFUSED"}]}})

    failures = gate.run_failures(report_path, collection_path)
    assert failures, "an errored request must be reported"
    assert failures[0][0] == target
    assert failures[0][0] != by_name_would_give


def test_the_gate_reports_even_when_an_earlier_step_failed():
    """The evaluation cannot run without its credential. If that stopped the job,
    every deterministic result would be hidden behind a configuration error."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    gate_step = next(s for s in workflow["jobs"]["verify"]["steps"]
                     if s.get("name") == "Decide whether the run passes")
    assert "cancelled()" in str(gate_step.get("if", "")), \
        "the gate must run after a failed step, or a missing secret hides the results"


def test_the_workflow_runs_the_tooling_s_own_tests():
    """The tooling decides whether a merge is sound, so CI has to check the
    tooling itself - not only what it reports about the API."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    steps = workflow["jobs"]["verify"]["steps"]
    assert any("pytest" in str(s.get("run", "")) for s in steps), \
        "no step runs the tooling's test suite"


def test_the_test_suite_needs_no_artefact_from_a_previous_run():
    """Everything the suite reads is either committed or generated by it."""
    committed = [HERE / "checks", HERE / "surfaces.yaml", HERE / "unobservable.yaml",
                 SPECS, WORKFLOW, HERE / "README.md"]
    for path in committed:
        assert path.exists(), path


# A body field the description does not declare means the request is rejected
# for the wrong reason and the requirement is never exercised. These pin that
# shut: it is the defect that reached review.


def test_every_check_sends_only_fields_the_description_declares(checks, generated_schema):
    schema = openapi.load(generated_schema)
    by_id = {o["operation_id"]: o for o in openapi.operations(schema)}
    for check in checks:
        for request in check.sequence:
            build.check_body_fields(schema, by_id, check.citation, request)


def test_a_body_field_the_operation_does_not_declare_is_refused(capabilities, tmp_path,
                                                                generated_schema):
    """Signing in with a `username` field, or signing up with `email_or_username`,
    reaches the endpoint and is refused for a reason unrelated to the
    requirement under test."""
    path = tmp_path / "c.yaml"
    path.write_text(
        "capability: user-signin\nchecks:\n  - requirement: Return HTTP 401 on rejection\n"
        "    sequence:\n      - name: x\n        operation: signin_create\n"
        "        body: {email_or_username: 'a', username: 'b', password: 'c'}\n"
    )
    check = library.load_file(path, capabilities)[0]
    schema = openapi.load(generated_schema)
    by_id = {o["operation_id"]: o for o in openapi.operations(schema)}
    with pytest.raises(ValueError, match="does not declare"):
        build.check_body_fields(schema, by_id, check.citation, check.sequence[0])


def test_a_missing_required_field_is_not_refused_at_build(capabilities, tmp_path,
                                                          generated_schema):
    """A field the API requires but no promoted spec describes is the divergence
    a run exists to report. Refusing to build it would suppress the finding."""
    path = tmp_path / "c.yaml"
    path.write_text(
        "capability: user-signup\nchecks:\n  - requirement: Accept a signup submission\n"
        "    sequence:\n      - name: x\n        operation: signup_create\n"
        "        body: {email: 'a@b.com', username: 'u_x', password: 'abcdef12'}\n"
    )
    check = library.load_file(path, capabilities)[0]
    schema = openapi.load(generated_schema)
    by_id = {o["operation_id"]: o for o in openapi.operations(schema)}
    build.check_body_fields(schema, by_id, check.citation, check.sequence[0])  # must not raise
