"""Read the promoted specs in openspec/specs/.

Expected behaviour comes from here and nowhere else. A check names the
requirement and scenario it verifies; this module supplies the text those names
must match, so a citation cannot drift from what the spec actually says.

Only promoted specs are read. A capability whose delta has not been archived is
not verified - a merge gate must not depend on work that may still change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REQUIREMENT = re.compile(r"^### Requirement:\s*(.+?)\s*$")
SCENARIO = re.compile(r"^#### Scenario:\s*(.+?)\s*$")


@dataclass(frozen=True)
class Scenario:
    name: str
    text: str


@dataclass(frozen=True)
class Requirement:
    capability: str
    name: str
    text: str
    scenarios: tuple[Scenario, ...]

    def scenario(self, name: str) -> Scenario | None:
        return next((s for s in self.scenarios if s.name == name), None)


@dataclass(frozen=True)
class Capability:
    name: str
    requirements: tuple[Requirement, ...]

    def requirement(self, name: str) -> Requirement | None:
        return next((r for r in self.requirements if r.name == name), None)


def _parse(capability: str, body: str) -> tuple[Requirement, ...]:
    requirements: list[Requirement] = []
    name = None
    lines: list[str] = []
    scenarios: list[Scenario] = []
    scenario_name = None
    scenario_lines: list[str] = []

    def close_scenario() -> None:
        nonlocal scenario_name, scenario_lines
        if scenario_name is not None:
            scenarios.append(Scenario(scenario_name, "\n".join(scenario_lines).strip()))
        scenario_name, scenario_lines = None, []

    def close_requirement() -> None:
        nonlocal name, lines, scenarios
        close_scenario()
        if name is not None:
            requirements.append(
                Requirement(capability, name, "\n".join(lines).strip(), tuple(scenarios))
            )
        name, lines, scenarios = None, [], []

    for line in body.splitlines():
        if match := REQUIREMENT.match(line):
            close_requirement()
            name = match.group(1)
            continue
        if match := SCENARIO.match(line):
            close_scenario()
            scenario_name = match.group(1)
            continue
        if scenario_name is not None:
            scenario_lines.append(line)
        elif name is not None:
            lines.append(line)

    close_requirement()
    return tuple(requirements)


def load(specs_root: Path) -> dict[str, Capability]:
    """Every promoted capability, keyed by name."""
    capabilities = {}
    for spec_file in sorted(specs_root.glob("*/spec.md")):
        capability = spec_file.parent.name
        capabilities[capability] = Capability(
            capability, _parse(capability, spec_file.read_text())
        )
    return capabilities
