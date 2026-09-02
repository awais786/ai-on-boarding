"""Prove the endpoint set complete against the addresses Django actually routes.

Deriving requests from the OpenAPI description keeps the endpoint set from going
stale, but only for surfaces the description knows about. This check closes the
remaining hole: every routed address must be accounted for by the description,
by a declaration, or by a written exclusion. Anything else fails the run and
names itself, so a new surface cannot be left unverified in silence.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verify import openapi, routes, surfaces

HERE = Path(__file__).resolve().parent.parent


def unaccounted(routed: list[dict], described: list[dict], declared: surfaces.Surfaces) -> list[str]:
    """Routed addresses that no source accounts for, as 'METHOD path' strings."""
    description_set = {(item["path"], item["method"]) for item in described}
    missing = []
    for address in routed:
        path = address["path"]
        if declared.excludes(path):
            continue
        for method in address["methods"]:
            if (path, method) in description_set:
                continue
            if declared.declares(path, method):
                continue
            missing.append(f"{method} {path}")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=HERE / "build" / "schema.yaml")
    parser.add_argument("--surfaces", type=Path, default=HERE / "surfaces.yaml")
    args = parser.parse_args(argv)

    declared = surfaces.load(args.surfaces)
    described = openapi.operations(openapi.load(args.schema))
    routed = routes.routed_addresses()

    missing = unaccounted(routed, described, declared)
    if missing:
        print("Coverage is not complete. These routed addresses are in neither the", file=sys.stderr)
        print("OpenAPI description, nor surfaces.yaml's declarations, nor its", file=sys.stderr)
        print("exclusions:", file=sys.stderr)
        for address in missing:
            print(f"  {address}", file=sys.stderr)
        print(file=sys.stderr)
        print("Add a check for it, declare it, or exclude it with a reason.", file=sys.stderr)
        return 1

    print(
        f"Coverage complete: {len(routed)} routed addresses, "
        f"{len(described)} described, {len(declared.declared)} declared, "
        f"{len(declared.excluded)} excluded."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
