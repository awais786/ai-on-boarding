"""Compare promoted requirements against the checks and the register.

Produces the coverage picture the gate and the evaluation both read: which
requirements and scenarios have a check, which are recorded as unobservable, and
which are neither - the last being the gap that must not pass unnoticed.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from verify import library as library_module
from verify import register as register_module
from verify import specs as specs_module


@dataclass(frozen=True)
class Gap:
    capability: str
    requirement: str
    scenario: str | None

    @property
    def citation(self) -> str:
        if self.scenario:
            return f"{self.capability}: {self.requirement} / {self.scenario}"
        return f"{self.capability}: {self.requirement}"


def gaps(
    capabilities: dict[str, specs_module.Capability],
    checks: list[library_module.Check],
    entries: list[register_module.Entry],
) -> list[Gap]:
    """Scenarios with neither a check nor a register entry."""
    checked = {(c.capability, c.requirement, c.scenario) for c in checks}
    checked_requirements = {(c.capability, c.requirement) for c in checks}
    recorded_scenarios = {e.key for e in entries if not e.partial}
    recorded_requirements = {
        (e.capability, e.requirement) for e in entries if e.scenario is None and not e.partial
    }

    found = []
    for capability in capabilities.values():
        for requirement in capability.requirements:
            if (capability.name, requirement.name) in recorded_requirements:
                continue
            if not requirement.scenarios:
                # Every requirement is meant to carry a scenario, but one that
                # does not must still be classified: without this the loop below
                # never runs and the requirement passes the gate unchecked and
                # unrecorded - the one shape the ratchet would not catch.
                if (capability.name, requirement.name) not in checked_requirements:
                    found.append(Gap(capability.name, requirement.name, None))
                continue
            for scenario in requirement.scenarios:
                key = (capability.name, requirement.name, scenario.name)
                if key in checked or key in recorded_scenarios:
                    continue
                # A check citing the requirement without naming a scenario
                # covers the requirement as a whole.
                if (capability.name, requirement.name) in checked_requirements and any(
                    c.scenario is None
                    for c in checks
                    if (c.capability, c.requirement) == (capability.name, requirement.name)
                ):
                    continue
                found.append(Gap(capability.name, requirement.name, scenario.name))
    return found


def summary(
    capabilities: dict[str, specs_module.Capability],
    checks: list[library_module.Check],
    entries: list[register_module.Entry],
) -> dict:
    found = gaps(capabilities, checks, entries)
    return {
        "capabilities": {
            name: {
                "requirements": len(cap.requirements),
                "scenarios": sum(len(r.scenarios) for r in cap.requirements),
            }
            for name, cap in capabilities.items()
        },
        "checks": len(checks),
        "register_entries": len(entries),
        "gaps": [asdict(g) for g in found],
    }
