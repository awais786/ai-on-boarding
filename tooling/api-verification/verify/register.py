"""Load and validate the register of requirements not observable over HTTP.

The register is the baseline the judged half of the gate ratchets against: a
reasoned, reviewed gap does not fail a run, but a requirement nobody has
classified does. That only holds if every entry resolves to a requirement that
actually exists and names a category from the fixed set, so both are enforced
here rather than trusted.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from verify import specs as specs_module

CATEGORIES = {"time-bound", "storage-internal", "induced-failure", "concurrency"}


class RegisterError(ValueError):
    """The register is not usable as written."""


@dataclass(frozen=True)
class Entry:
    capability: str
    requirement: str
    scenario: str | None
    category: str
    reason: str
    covered_by: str
    partial: bool

    @property
    def key(self) -> tuple[str, str, str | None]:
        return (self.capability, self.requirement, self.scenario)


def load(path: Path, capabilities: dict[str, specs_module.Capability]) -> list[Entry]:
    raw = yaml.safe_load(path.read_text()) or {}
    entries = []
    for item in raw.get("entries") or []:
        capability = item.get("capability")
        promoted = capabilities.get(capability)
        if promoted is None:
            raise RegisterError(
                f"register entry names capability {capability!r}, which is not promoted"
            )
        requirement_name = item.get("requirement")
        requirement = promoted.requirement(requirement_name)
        if requirement is None:
            raise RegisterError(
                f"register entry names requirement {requirement_name!r}, which does not "
                f"appear in openspec/specs/{capability}/spec.md"
            )
        scenario_name = item.get("scenario")
        if scenario_name is not None and requirement.scenario(scenario_name) is None:
            raise RegisterError(
                f"register entry names scenario {scenario_name!r} under requirement "
                f"{requirement_name!r}, which does not appear in that requirement"
            )
        category = item.get("category")
        if category not in CATEGORIES:
            raise RegisterError(
                f"register entry for {requirement_name!r} names category {category!r}; "
                f"it must be one of {sorted(CATEGORIES)}"
            )
        reason = (item.get("reason") or "").strip()
        if not reason:
            raise RegisterError(f"register entry for {requirement_name!r} states no reason")
        covered_by = (item.get("covered_by") or "").strip()
        if not covered_by:
            raise RegisterError(
                f"register entry for {requirement_name!r} names no test covering it "
                "instead; an entry is a division of labour, not an exemption"
            )
        entries.append(
            Entry(
                capability,
                requirement_name,
                scenario_name,
                category,
                reason,
                covered_by,
                bool(item.get("partial", False)),
            )
        )
    return entries
