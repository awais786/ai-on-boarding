"""Judge the checks and their results against the promoted specs.

The deterministic half of the gate answers "did a check fail". This step answers
the question a passing report cannot: are the checks a faithful reading of what
the specs require, and is anything left unchecked. It reports requirements with
no check, checks that state something other than the requirement they name, and
endpoints checked only for a status code where their spec states more.

The reply is constrained to a fixed shape, so the gate reads findings rather
than parsing prose. A finding either names a promoted requirement or names none;
that distinction is what decides whether it blocks, and it is the same one this
project already applies to code review findings.

If the credential is missing the step fails and says so. It never reports
success with the evaluation skipped: a gate that silently stops running is worse
than no gate, because it still reports green.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from verify import coverage, library as library_module, openapi, register, specs

HERE = Path(__file__).resolve().parent.parent
MODEL = "claude-opus-5"
CREDENTIAL = "ANTHROPIC_API_KEY"


class EvaluationUnavailable(RuntimeError):
    """The evaluation could not be performed."""


class Finding(BaseModel):
    kind: Literal["missing_check", "misstated_check", "status_only", "violation"]
    capability: str = Field(default="", description="Capability, or empty if none applies.")
    requirement: str = Field(
        default="",
        description=(
            "The promoted requirement's name, copied verbatim. Empty when the finding "
            "names no requirement - such a finding is recorded but does not block."
        ),
    )
    scenario: str = Field(default="", description="The scenario's name, or empty.")
    summary: str = Field(description="One sentence stating the finding.")
    detail: str = Field(description="Why this follows from the spec text and the evidence.")


class Findings(BaseModel):
    findings: list[Finding]


def gather(
    specs_root: Path, checks_root: Path, register_path: Path, report_path: Path, schema_path: Path
) -> dict:
    """The evidence the evaluation reads, compacted to what it needs to judge."""
    capabilities = specs.load(specs_root)
    checks = library_module.load(checks_root, capabilities)
    entries = register.load(register_path, capabilities)

    results: dict[str, dict] = collections.defaultdict(
        lambda: {"passed": 0, "failed": 0, "failures": []}
    )
    if report_path.exists():
        report = json.loads(report_path.read_text())
        from verify import gate

        for citation, message in gate.run_failures(report_path, report_path.parent / "collection.json"):
            results[citation]["failed"] += 1
            if message not in results[citation]["failures"]:
                results[citation]["failures"].append(message)
        for execution in report.get("run", {}).get("executions", []):
            for assertion in execution.get("assertions", []) or []:
                if not assertion.get("error") and not assertion.get("skipped"):
                    results[assertion["assertion"].split(" :: ")[0]]["passed"] += 1

    return {
        "promoted_requirements": [
            {
                "capability": capability.name,
                "requirement": requirement.name,
                "text": requirement.text,
                "scenarios": [{"name": s.name, "text": s.text} for s in requirement.scenarios],
            }
            for capability in capabilities.values()
            for requirement in capability.requirements
        ],
        "checks": [
            {
                "capability": check.capability,
                "requirement": check.requirement,
                "scenario": check.scenario,
                "citation": check.citation,
                "requests": [
                    {
                        "name": request.name,
                        "addresses": request.operation or request.surface or request.url,
                        "body": request.body or request.form,
                        "assertions": list(request.assertions),
                    }
                    for request in check.sequence
                ],
            }
            for check in checks
        ],
        "unobservable_register": [
            {
                "capability": e.capability,
                "requirement": e.requirement,
                "scenario": e.scenario,
                "category": e.category,
                "partial": e.partial,
                "reason": e.reason,
            }
            for e in entries
        ],
        "described_operations": openapi.operations(openapi.load(schema_path))
        if schema_path.exists()
        else [],
        "run_results": dict(results),
        "coverage_gaps": coverage.summary(capabilities, checks, entries)["gaps"],
    }


PROMPT = """\
You are evaluating an automated verification of a running HTTP API against its written
specifications. Your job is to judge whether the checks are a faithful reading of the specs
and whether anything specified is left unchecked. You are not reviewing the API's design.

You are given:
- `promoted_requirements`: the specifications. These are the only source of expected behaviour.
- `checks`: the behavioural checks, each naming the requirement and scenario it claims to verify.
- `unobservable_register`: requirements and scenarios recorded as impossible to judge over HTTP,
  with the reason. These are NOT gaps; do not report them as missing.
- `described_operations`: the endpoints the API's OpenAPI description exposes.
- `run_results`: what happened when the checks ran, per check, including failure messages.
- `coverage_gaps`: scenarios computed to have neither a check nor a register entry.

Report findings of these kinds:
- `missing_check`: a promoted requirement or scenario that applies to a verified endpoint, has no
  check, and is not in the register.
- `misstated_check`: a check whose assertions verify something other than what the requirement it
  names actually says - including a check that would pass while the requirement is violated, or
  that asserts something the requirement does not state.
- `status_only`: an endpoint whose spec states behaviour beyond a successful response, but whose
  checks assert only a status code.
- `violation`: a run result showing the live API answering in a way a promoted requirement says
  it must not.

Rules:
- When a finding concerns a specific promoted requirement, copy its name into `requirement`
  VERBATIM, and its capability into `capability`. Add `scenario` when it concerns one scenario.
- When a finding concerns no specific requirement, leave `requirement` empty. Such findings are
  recorded but do not block a merge, so do not attach a requirement name you are unsure of.
- Do not invent requirements. Only names appearing in `promoted_requirements` are valid.
- Report nothing for a requirement or scenario present in `unobservable_register`.
- Be precise and sparing. A finding that cannot be traced to spec text is noise.

Return findings only.
"""


def evaluate(evidence: dict, model: str = MODEL) -> Findings:
    if not os.environ.get(CREDENTIAL):
        raise EvaluationUnavailable(
            f"{CREDENTIAL} is not set, so the checks cannot be evaluated against the specs. "
            "This run fails rather than passing with the evaluation skipped - a gate that "
            "silently stops running still reports green. A maintainer must add "
            f"{CREDENTIAL} to the repository's secrets."
        )
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_format=Findings,
        messages=[
            {
                "role": "user",
                "content": PROMPT + "\n\nEvidence:\n" + json.dumps(evidence, indent=1),
            }
        ],
    )
    return response.parsed_output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs", type=Path, default=HERE.parent.parent / "openspec" / "specs")
    parser.add_argument("--checks", type=Path, default=HERE / "checks")
    parser.add_argument("--register", type=Path, default=HERE / "unobservable.yaml")
    parser.add_argument("--report", type=Path, default=HERE / "build" / "report.json")
    parser.add_argument("--schema", type=Path, default=HERE / "build" / "schema.yaml")
    parser.add_argument("--out", type=Path, default=HERE / "build" / "findings.json")
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args(argv)

    evidence = gather(args.specs, args.checks, args.register, args.report, args.schema)
    try:
        findings = evaluate(evidence, args.model)
    except EvaluationUnavailable as unavailable:
        print(f"Evaluation could not be performed: {unavailable}", file=sys.stderr)
        return 2

    args.out.write_text(findings.model_dump_json(indent=2) + "\n")
    named = sum(1 for f in findings.findings if f.requirement)
    print(
        f"Evaluation wrote {args.out} - {len(findings.findings)} findings, "
        f"{named} naming a requirement."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
