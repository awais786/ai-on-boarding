"""Enumerate every address the Django application routes.

Deriving the collection from the OpenAPI description answers "which API
endpoints exist". It does not answer "which HTTP surfaces exist" - a surface
served outside the API framework is absent from the description by design. This
module supplies the second list so the completeness check can compare them.

Runs inside the Django environment; everything else in this tooling does not.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DJANGO_PROJECT = REPO_ROOT / "sdd_django_demo"


def _setup_django() -> None:
    sys.path.insert(0, str(DJANGO_PROJECT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sdd_django_demo.settings")
    import django

    django.setup()


def _methods_for(callback) -> list[str]:
    """The HTTP methods a view answers.

    A view class - whether Django's or the API framework's - names its allowed
    methods and defines a handler per method it actually implements. Taking the
    intersection avoids reporting the full default method list for a view that
    only implements one of them.
    """
    view_class = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
    if view_class is None:
        # A plain function view. Django routes every method to it and lets the
        # view decide, and nothing here can narrow that down. Reporting only GET
        # would let its other methods slip past the completeness check
        # unaccounted for, so report them all: the cost is having to classify a
        # method that turns out to be unreachable, which is a decision someone
        # writes down rather than a hole nobody sees.
        return ["DELETE", "GET", "PATCH", "POST", "PUT"]
    allowed = getattr(view_class, "http_method_names", [])
    return sorted(
        method.upper()
        for method in allowed
        if method != "options" and hasattr(view_class, method)
    )


def _walk(patterns, prefix: str, found: list[dict]) -> None:
    from django.urls import URLPattern, URLResolver

    for entry in patterns:
        path = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            _walk(entry.url_patterns, path, found)
        elif isinstance(entry, URLPattern):
            found.append({"path": "/" + path.lstrip("/"), "methods": _methods_for(entry.callback)})


def routed_addresses() -> list[dict]:
    """Every routed address, as a path and the methods it answers."""
    _setup_django()
    from django.urls import get_resolver

    found: list[dict] = []
    _walk(get_resolver().url_patterns, "", found)
    return sorted(found, key=lambda item: item["path"])


def main() -> int:
    json.dump(routed_addresses(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
