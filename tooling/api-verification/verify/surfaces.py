"""Load and validate the declared and excluded HTTP surfaces.

An exclusion without a reason is the failure this file exists to prevent: it
would let a surface drop out of verification silently, which is the same
staleness that hand-maintaining the endpoint list would have caused.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class SurfacesError(ValueError):
    """The declarations are not usable as written."""


@dataclass(frozen=True)
class Declared:
    path: str
    methods: tuple[str, ...]
    capability: str
    reason: str


@dataclass(frozen=True)
class Excluded:
    reason: str
    path: str | None = None
    prefix: str | None = None

    def matches(self, path: str) -> bool:
        if self.prefix is not None:
            return path.startswith(self.prefix)
        return path == self.path


@dataclass(frozen=True)
class Surfaces:
    declared: tuple[Declared, ...] = field(default_factory=tuple)
    excluded: tuple[Excluded, ...] = field(default_factory=tuple)

    def declares(self, path: str, method: str) -> bool:
        return any(d.path == path and method in d.methods for d in self.declared)

    def excludes(self, path: str) -> bool:
        return any(e.matches(path) for e in self.excluded)


def _require_reason(entry: dict, label: str) -> str:
    reason = (entry.get("reason") or "").strip()
    if not reason:
        raise SurfacesError(f"{label} has no reason; every entry must state why")
    return reason


def load(path: Path) -> Surfaces:
    with path.open() as handle:
        raw = yaml.safe_load(handle) or {}

    declared = []
    for entry in raw.get("declared") or []:
        address = entry.get("path")
        if not address:
            raise SurfacesError("a declared surface has no path")
        methods = tuple(m.upper() for m in (entry.get("methods") or []))
        if not methods:
            raise SurfacesError(f"declared surface {address} names no methods")
        capability = (entry.get("capability") or "").strip()
        if not capability:
            raise SurfacesError(
                f"declared surface {address} names no capability; a declared surface "
                "is declared because it carries requirements, so it must say whose"
            )
        declared.append(
            Declared(address, methods, capability, _require_reason(entry, f"declared {address}"))
        )

    excluded = []
    for entry in raw.get("excluded") or []:
        address, prefix = entry.get("path"), entry.get("prefix")
        if bool(address) == bool(prefix):
            raise SurfacesError("an excluded surface must name exactly one of path or prefix")
        label = f"excluded {address or prefix}"
        excluded.append(Excluded(_require_reason(entry, label), address, prefix))

    return Surfaces(tuple(declared), tuple(excluded))
