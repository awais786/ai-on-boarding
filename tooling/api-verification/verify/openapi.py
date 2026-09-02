"""Read the generated OpenAPI description.

The description is the source of the endpoint set: what it lists is what the
collection exercises. Generation itself is a command in the run script - this
module only reads what that command produced.
"""
from __future__ import annotations

from pathlib import Path

import yaml

HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}


def load(schema_path: Path) -> dict:
    with schema_path.open() as handle:
        return yaml.safe_load(handle)


def operations(schema: dict) -> list[dict]:
    """Every operation the description exposes, as path, method and operationId."""
    found = []
    for path, item in (schema.get("paths") or {}).items():
        for method, operation in item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            found.append(
                {
                    "path": path,
                    "method": method.upper(),
                    "operation_id": operation.get("operationId", ""),
                }
            )
    return sorted(found, key=lambda item: (item["path"], item["method"]))
