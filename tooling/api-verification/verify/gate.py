"""Decide whether a verification run passes.

Two halves. The deterministic half fails on things that are simply true or not:
coverage is incomplete, a check failed against the live API, or the evaluation
did not run. The judged half fails on an evaluation finding that names a
promoted requirement - unless that requirement is recorded as unobservable, in
which case it was reasoned about in a reviewed file and does not block.

That combination is a ratchet. A gap someone has classified stays classified; a
requirement nobody has classified fails the run. A finding naming no requirement
is reported and does not block, which is the distinction this project already
draws between a blocking review finding and a nit.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from verify import completeness, coverage, library, register, specs

HERE = Path(__file__).resolve().parent.parent


def _citations(collection_path: Path) -> dict[str, str]:
    """Request id -> the citation of the check it belongs to.

    Keyed on the id the builder assigns, not on the request's name: names repeat
    across checks - "create the account" opens 35 different sequences - so a
    name-keyed map would file a failed request under whichever check was built
    last. A failure has to name the requirement its own check verifies.
    """
    if not collection_path.exists():
        return {}
    collection = json.loads(collection_path.read_text())
    return {
        item["id"]: folder["name"]
        for folder in collection.get("item", [])
        for item in folder.get("item", [])
        if item.get("id")
    }


def run_failures(report_path: Path, collection_path: Path) -> list[tuple[str, str]]:
    """Everything that went wrong in the run, as (citation, message).

    A failed assertion is only one way a check can fail to hold. A request that
    never reached the server, or a test script that threw before reaching its
    assertions, records NO assertions at all - so reading assertion errors alone
    cannot tell a check that never ran from a check that passed. Both are
    collected here, along with a run-level error, because "Every check produces a
    recorded outcome" is not satisfied by an outcome that was never recorded.

    A request with no assertions and no error is not a failure: sequences carry
    setup and capture steps that assert nothing by design.
    """
    report = json.loads(report_path.read_text())
    run = report.get("run", {})
    names = _citations(collection_path)
    failures: list[tuple[str, str]] = []

    if run.get("error"):
        failures.append(("the run itself", str(run["error"])))

    for execution in run.get("executions", []):
        item = execution.get("item") or {}
        item_name = item.get("name", "an unnamed request")
        # Falls back to the request's own name only when the id is absent, which
        # names something rather than misattributing it to another check.
        where = names.get(item.get("id"), item_name)

        if execution.get("requestError"):
            failures.append(
                (where, f"the request never completed: {execution['requestError']} "
                        f"({item_name})")
            )
        for script in execution.get("testScript") or []:
            if script.get("error"):
                message = (script["error"] or {}).get("message", script["error"])
                failures.append(
                    (where, f"the test script threw before its assertions could run: "
                            f"{message} ({item_name})")
                )
        for assertion in execution.get("assertions", []) or []:
            citation = assertion["assertion"].split(" :: ")[0]
            if assertion.get("error"):
                failures.append((citation, assertion["error"].get("message", "")))
            elif assertion.get("skipped"):
                failures.append((citation, f"the check was skipped, not run ({item_name})"))
    return failures


def blocking_findings(findings: list[dict], entries: list[register.Entry]) -> list[dict]:
    """Findings that name a requirement not recorded as unobservable."""
    recorded_scenarios = {e.key for e in entries if not e.partial}
    recorded_requirements = {
        (e.capability, e.requirement) for e in entries if e.scenario is None and not e.partial
    }
    blocking = []
    for finding in findings:
        requirement = (finding.get("requirement") or "").strip()
        if not requirement:
            continue  # names no requirement: recorded, never blocking
        capability = (finding.get("capability") or "").strip()
        scenario = (finding.get("scenario") or "").strip() or None
        if (capability, requirement) in recorded_requirements:
            continue
        if (capability, requirement, scenario) in recorded_scenarios:
            continue
        blocking.append(finding)
    return blocking


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=HERE / "build" / "report.json")
    parser.add_argument("--findings", type=Path, default=HERE / "build" / "findings.json")
    parser.add_argument("--schema", type=Path, default=HERE / "build" / "schema.yaml")
    parser.add_argument("--surfaces", type=Path, default=HERE / "surfaces.yaml")
    parser.add_argument("--register", type=Path, default=HERE / "unobservable.yaml")
    parser.add_argument("--checks", type=Path, default=HERE / "checks")
    parser.add_argument("--collection", type=Path, default=HERE / "build" / "collection.json")
    parser.add_argument("--specs", type=Path, default=HERE.parent.parent / "openspec" / "specs")
    parser.add_argument(
        "--skip-completeness",
        action="store_true",
        help="The run script already ran it; do not repeat the Django import.",
    )
    args = parser.parse_args(argv)

    reasons: list[str] = []

    if not args.skip_completeness:
        if completeness.main(["--schema", str(args.schema), "--surfaces", str(args.surfaces)]):
            reasons.append("coverage is not complete against the routed addresses")

    if not args.report.exists():
        reasons.append(f"no run report at {args.report}; the collection did not execute")
    else:
        failures = run_failures(args.report, args.collection)
        if failures:
            reasons.append(f"{len(failures)} check(s) failed or did not run")
            print("Checks that failed or did not run:", file=sys.stderr)
            for citation, message in failures:
                print(f"  {citation}\n      {message}", file=sys.stderr)
            print(file=sys.stderr)

    # A requirement with neither a check nor a register entry is a gap whether or
    # not the evaluation runs. Deciding it here keeps it off the model's critical
    # path: the judged half adds findings, it is not the only thing that reports.
    capabilities = specs.load(args.specs)
    entries = register.load(args.register, capabilities)
    unclassified = coverage.gaps(capabilities, library.load(args.checks, capabilities), entries)
    if unclassified:
        reasons.append(f"{len(unclassified)} requirement(s) have neither a check nor a register entry")
        print("Requirements with neither a check nor a register entry:", file=sys.stderr)
        for gap in unclassified:
            print(f"  {gap.citation}", file=sys.stderr)
        print(file=sys.stderr)

    if not args.findings.exists():
        reasons.append(
            f"no evaluation findings at {args.findings}; the evaluation did not run, and a "
            "run does not pass with it skipped"
        )
    else:
        findings = json.loads(args.findings.read_text()).get("findings", [])
        blocking = blocking_findings(findings, entries)
        nits = len(findings) - len(blocking)
        if blocking:
            reasons.append(f"{len(blocking)} evaluation finding(s) name a promoted requirement")
            print("Evaluation findings that name a requirement:", file=sys.stderr)
            for finding in blocking:
                print(
                    f"  [{finding.get('kind')}] {finding.get('capability')}: "
                    f"{finding.get('requirement')}"
                    + (f" / {finding['scenario']}" if finding.get("scenario") else ""),
                    file=sys.stderr,
                )
                print(f"      {finding.get('summary')}", file=sys.stderr)
            print(file=sys.stderr)
        if nits:
            print(f"{nits} evaluation finding(s) name no requirement; recorded, not blocking.")

    if reasons:
        print("Verification failed:", file=sys.stderr)
        for reason in reasons:
            print(f"  - {reason}", file=sys.stderr)
        return 1

    print("Verification passed: coverage complete, every check held, no blocking finding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
