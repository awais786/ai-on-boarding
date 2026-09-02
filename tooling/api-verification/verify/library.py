"""Load and validate the behavioural check library.

Format
------
One file per capability under `checks/`, mirroring `openspec/specs/`. Each entry
names, verbatim, the requirement and scenario it verifies, so a citation can be
matched against the promoted text rather than trusted. An entry holds an ordered
sequence of requests: many requirements are only observable across more than one
(two refusals compared with each other, a reset followed by a signin). A
single-request check is a sequence of length one.

    capability: user-signin
    checks:
      - requirement: Return HTTP 401 on rejection      # must exist in the spec
        scenario: Rejection status code                # must exist in that requirement
        sequence:
          - name: sign in with a wrong password
            operation: signin_create                   # an OpenAPI operationId
            body: {email: "{{addr}}", password: "wrong"}
            assert:
              - {status: 401}

A request addresses either an `operation` (an operationId from the description)
or a `surface` (a path and method declared in surfaces.yaml). It may `save_as` a
name so a later request can compare against it, and `capture` values out of a
response into variables that later requests interpolate as `{{name}}`.

Assertion kinds
---------------
    status          the response status equals this
    json_has        the response body is JSON carrying this key (dotted path)
    json_equals     that key holds this value
    json_lacks      the response body carries no such key, at any depth
    body_includes   the raw response text contains this (after interpolation)
    body_excludes   the raw response text does not contain this
    same_as         status and body are both identical to a saved response
    saved_excludes  a saved response's text does not contain this value
    header_absent   the response carries no such header
    body_count      the raw response text contains this pattern exactly this many times
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from verify import specs as specs_module

ASSERTION_KINDS = {
    "status",
    "json_has",
    "json_equals",
    "json_lacks",
    "json_only_keys",
    "body_includes",
    "body_excludes",
    "same_as",
    "saved_excludes",
    "header_absent",
    "body_count",
}


class LibraryError(ValueError):
    """The library is not usable as written."""


@dataclass(frozen=True)
class Request:
    name: str
    operation: str | None
    surface: dict | None
    body: dict | None
    form: dict | None
    path_params: dict
    query: dict
    url: str | None
    save_as: str | None
    capture: tuple[dict, ...]
    assertions: tuple[dict, ...]


@dataclass(frozen=True)
class Check:
    capability: str
    requirement: str
    scenario: str | None
    sequence: tuple[Request, ...]

    @property
    def citation(self) -> str:
        if self.scenario:
            return f"{self.capability}: {self.requirement} / {self.scenario}"
        return f"{self.capability}: {self.requirement}"


def _request(raw: dict, where: str) -> Request:
    name = (raw.get("name") or "").strip()
    if not name:
        raise LibraryError(f"{where}: a request has no name")
    operation, surface, url = raw.get("operation"), raw.get("surface"), raw.get("url")
    if sum(bool(x) for x in (operation, surface, url)) != 1:
        raise LibraryError(
            f"{where}: request {name!r} must address exactly one of "
            "operation, surface or url"
        )
    assertions = tuple(raw.get("assert") or ())
    for assertion in assertions:
        unknown = set(assertion) - ASSERTION_KINDS
        if unknown:
            raise LibraryError(
                f"{where}: request {name!r} uses unknown assertion(s) {sorted(unknown)}"
            )
        # One kind per entry. `- {status: 400, json_has: email}` is a single
        # two-key mapping and reads like two assertions, but only one could be
        # emitted - so the other would be silently dropped and never checked.
        if len(assertion) != 1:
            raise LibraryError(
                f"{where}: request {name!r} has an assertion naming {len(assertion)} kinds "
                f"({sorted(assertion)}); write one kind per list entry, or one would be "
                "dropped without being checked"
            )
    return Request(
        name=name,
        operation=operation,
        surface=surface,
        body=raw.get("body"),
        form=raw.get("form"),
        path_params=raw.get("path_params") or {},
        query=raw.get("query") or {},
        url=url,
        save_as=raw.get("save_as"),
        capture=tuple(raw.get("capture") or ()),
        assertions=assertions,
    )


def load_file(path: Path, capabilities: dict[str, specs_module.Capability]) -> list[Check]:
    raw = yaml.safe_load(path.read_text()) or {}
    capability = raw.get("capability")
    if capability not in capabilities:
        raise LibraryError(
            f"{path.name}: names capability {capability!r}, which is not a promoted "
            f"spec. Promoted capabilities are {sorted(capabilities)}."
        )
    promoted = capabilities[capability]

    checks = []
    for entry in raw.get("checks") or []:
        requirement_name = entry.get("requirement")
        requirement = promoted.requirement(requirement_name)
        if requirement is None:
            raise LibraryError(
                f"{path.name}: cites requirement {requirement_name!r}, which does not "
                f"appear in openspec/specs/{capability}/spec.md"
            )
        scenario_name = entry.get("scenario")
        if scenario_name is not None and requirement.scenario(scenario_name) is None:
            raise LibraryError(
                f"{path.name}: cites scenario {scenario_name!r} under requirement "
                f"{requirement_name!r}, which does not appear in that requirement"
            )
        where = f"{path.name} [{requirement_name}]"
        sequence = tuple(_request(item, where) for item in entry.get("sequence") or ())
        if not sequence:
            raise LibraryError(f"{where}: has no requests")
        checks.append(Check(capability, requirement_name, scenario_name, sequence))
    return checks


def load(checks_root: Path, capabilities: dict[str, specs_module.Capability]) -> list[Check]:
    checks: list[Check] = []
    for path in sorted(checks_root.glob("*.yaml")):
        checks.extend(load_file(path, capabilities))
    return checks
