"""Assemble the collection the run executes.

Three sources meet here. The OpenAPI description supplies the endpoint set, via
the converter's output - no endpoint is named by hand. The check library
supplies request data, ordering, and the assertions, each carrying the
requirement it verifies into the test's own name so a failure in the report
points back at the spec. surfaces.yaml supplies the addresses the description
omits.

Any operation or declared surface no check refers to still gets a request
asserting the status codes the description documents for it, so nothing in the
collection is executed without being checked.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from verify import library as library_module
from verify import openapi, register, specs, surfaces

HERE = Path(__file__).resolve().parent.parent
DJANGO_PARAM = re.compile(r"<[^:>]+:([^>]+)>")


def _js(value) -> str:
    """A JavaScript literal for a Python value."""
    return json.dumps(value)


def _resolve(value: str) -> str:
    """JS that expands {{variables}} in a string at test time."""
    return f"pm.variables.replaceIn({_js(value)})"


def _assertion_js(assertion: dict, test_name: str) -> list[str]:
    name = _js(test_name)
    if "status" in assertion:
        return [f"pm.test({name}, function () {{ pm.response.to.have.status({assertion['status']}); }});"]
    if "json_has" in assertion:
        path = _js(assertion["json_has"])
        return [
            f"pm.test({name}, function () {{",
            f"  pm.expect(readPath(pm.response.json(), {path})).to.not.equal(undefined);",
            "});",
        ]
    if "json_equals" in assertion:
        spec = assertion["json_equals"]
        path, value = _js(spec["path"]), spec["value"]
        expected = _resolve(value) if isinstance(value, str) else _js(value)
        return [
            f"pm.test({name}, function () {{",
            f"  pm.expect(readPath(pm.response.json(), {path})).to.eql({expected});",
            "});",
        ]
    if "json_lacks" in assertion:
        key = _js(assertion["json_lacks"])
        return [
            f"pm.test({name}, function () {{",
            f"  pm.expect(hasKeyAnywhere(pm.response.json(), {key})).to.equal(false);",
            "});",
        ]
    if "json_only_keys" in assertion:
        keys = _js(sorted(assertion["json_only_keys"]))
        return [
            f"pm.test({name}, function () {{",
            f"  pm.expect(Object.keys(pm.response.json()).sort()).to.eql({keys});",
            "});",
        ]
    if "body_includes" in assertion:
        return [
            f"pm.test({name}, function () {{",
            f"  pm.expect(pm.response.text()).to.include({_resolve(assertion['body_includes'])});",
            "});",
        ]
    if "body_excludes" in assertion:
        return [
            f"pm.test({name}, function () {{",
            f"  pm.expect(pm.response.text()).to.not.include({_resolve(assertion['body_excludes'])});",
            "});",
        ]
    if "body_count" in assertion:
        spec = assertion["body_count"]
        return [
            f"pm.test({name}, function () {{",
            f"  pm.expect(countOf(pm.response.text(), {_resolve(spec['pattern'])}))"
            f".to.equal({spec['count']});",
            "});",
        ]
    if "header_absent" in assertion:
        return [
            f"pm.test({name}, function () {{",
            f"  pm.expect(pm.response.headers.has({_js(assertion['header_absent'])}))"
            ".to.equal(false);",
            "});",
        ]
    if "same_as" in assertion:
        saved = _js(assertion["same_as"])
        return [
            f"pm.test({name}, function () {{",
            f"  var other = loadSaved({saved});",
            "  pm.expect(pm.response.code).to.equal(other.status);",
            "  pm.expect(pm.response.text()).to.equal(other.body);",
            "});",
        ]
    if "saved_excludes" in assertion:
        spec = assertion["saved_excludes"]
        return [
            f"pm.test({name}, function () {{",
            f"  var other = loadSaved({_js(spec['saved'])});",
            f"  pm.expect(other.body).to.not.include({_resolve(spec['value'])});",
            "});",
        ]
    raise ValueError(f"no JavaScript defined for assertion {assertion!r}")


CSRF_CAPTURE = [
    "var hidden = pm.response.text().match(",
    "  /name=\"csrfmiddlewaretoken\"\\s+value=\"([^\"]+)\"/);",
    "if (hidden) {",
    "  pm.collectionVariables.set('csrfToken', hidden[1]);",
    "} else {",
    "  var cookie = pm.cookies.get('csrftoken');",
    "  if (cookie) { pm.collectionVariables.set('csrfToken', cookie); }",
    "}",
]

HELPERS = [
    "function readPath(obj, path) {",
    "  return String(path).split('.').reduce(function (acc, part) {",
    "    if (acc === undefined || acc === null) { return undefined; }",
    "    return acc[part];",
    "  }, obj);",
    "}",
    "function hasKeyAnywhere(obj, key) {",
    "  if (obj === null || typeof obj !== 'object') { return false; }",
    "  if (!Array.isArray(obj) && Object.prototype.hasOwnProperty.call(obj, key)) { return true; }",
    "  return Object.values(obj).some(function (v) { return hasKeyAnywhere(v, key); });",
    "}",
    "function countOf(text, needle) {",
    "  if (!needle) { return 0; }",
    "  return text.split(needle).length - 1;",
    "}",
    "function loadSaved(name) {",
    "  var raw = pm.collectionVariables.get('saved:' + name);",
    "  if (!raw) { throw new Error('no saved response named ' + name); }",
    "  return JSON.parse(raw);",
    "}",
]


def _script_for(request: library_module.Request, citation: str) -> list[str]:
    lines = list(HELPERS)
    if request.save_as:
        lines += [
            f"pm.collectionVariables.set('saved:' + {_js(request.save_as)}, JSON.stringify(",
            "  { status: pm.response.code, body: pm.response.text() }));",
        ]
    for capture in request.capture:
        var = _js(capture["var"])
        if "json" in capture:
            lines += [
                f"var picked = readPath(pm.response.json(), {_js(capture['json'])});",
                # Asserted rather than stringified blindly: String(undefined) is
                # "undefined", which later requests would carry into a URL and
                # blame the resulting 404 on the requirement under test.
                f"pm.test({_js(citation + ' :: a value could be read from the response')},"
                " function () { pm.expect(picked, 'path resolved to nothing')"
                ".to.not.equal(undefined); });",
                f"if (picked !== undefined && picked !== null) "
                f"{{ pm.collectionVariables.set({var}, String(picked)); }}",
            ]
        elif "regex" in capture:
            lines += [
                f"var m = pm.response.text().match(new RegExp({_js(capture['regex'])}));",
                f"pm.test({_js(citation + ' :: a value could be read from the response')},"
                " function () { pm.expect(m, 'pattern did not match').to.not.equal(null); });",
                f"if (m) {{ pm.collectionVariables.set({var}, m[1]); }}",
            ]
        else:
            raise ValueError(f"capture must name json or regex: {capture!r}")
    for assertion in request.assertions:
        kind = next(iter(assertion))
        lines += _assertion_js(assertion, f"{citation} :: {kind}")
    return lines


def declared_properties(schema: dict, operation: dict) -> set[str] | None:
    """The fields the description says an operation's request body may carry.

    Returns None when the operation declares no body, so a caller can tell
    "no constraint recorded" from "constrained to nothing".
    """
    path_item = (schema.get("paths") or {}).get(operation["path"]) or {}
    body = (path_item.get(operation["method"].lower()) or {}).get("requestBody")
    if not body:
        return None
    content = (body.get("content") or {}).get("application/json") or {}
    ref = (content.get("schema") or {}).get("$ref")
    if not ref:
        return None
    name = ref.rsplit("/", 1)[-1]
    component = ((schema.get("components") or {}).get("schemas") or {}).get(name) or {}
    return set(component.get("properties") or {})


def check_body_fields(schema: dict, operations: dict, check_citation: str, request) -> None:
    """Refuse a request body carrying a field the operation does not declare.

    A field the description has never heard of is a mistake in the check, not a
    finding about the API: the request is rejected for the wrong reason and the
    requirement it claims to verify is never exercised. Missing fields are NOT
    checked here - an operation requiring something no promoted spec describes is
    exactly the divergence a run is meant to report, and refusing to build it
    would suppress the finding.
    """
    if not request.operation:
        return
    body = request.body if request.body is not None else request.form
    if not body:
        return
    operation = operations.get(request.operation)
    if operation is None:
        return
    declared = declared_properties(schema, operation)
    if declared is None:
        return
    unknown = set(body) - declared
    if unknown:
        raise ValueError(
            f"{check_citation}: request {request.name!r} sends "
            f"{sorted(unknown)} to {request.operation}, which the OpenAPI description "
            f"does not declare. It accepts {sorted(declared)}. The request would be "
            "rejected for the wrong reason and the requirement never exercised."
        )


def _url_for(raw: str) -> str:
    """Postman parses a plain string; an object carrying only `raw` it does not."""
    return raw


def _form_fetch_item(raw_url: str, name: str) -> dict:
    """Fetch the form before submitting it.

    The page's form carries a CSRF token, so a submission that never fetched the
    form is refused before the view runs - which would verify Django's CSRF
    protection rather than the requirement under test. A person submitting this
    form has always been served it first; this request is that step.
    """
    return {
        "name": name,
        "request": {"method": "GET", "header": [], "url": _url_for(raw_url)},
        "event": [
            {
                "listen": "test",
                "script": {"type": "text/javascript", "exec": list(CSRF_CAPTURE)},
            }
        ],
    }


def _item(request: library_module.Request, citation: str, derived: dict) -> dict:
    if request.url:
        method, raw_url = "GET", request.url
        headers = []
    elif request.surface:
        method = request.surface["method"].upper()
        path = request.surface["path"]
        for name, value in request.path_params.items():
            path = DJANGO_PARAM.sub(lambda m: value if m.group(1) == name else m.group(0), path)
        raw_url = "{{baseUrl}}" + path
        headers = []
    else:
        source = derived.get(request.operation)
        if source is None:
            raise ValueError(f"no operation {request.operation!r} in the OpenAPI description")
        method = source["method"]
        raw_url = "{{baseUrl}}" + source["path"]
        headers = []

    if request.query:
        pairs = "&".join(f"{k}={v}" for k, v in request.query.items())
        raw_url = f"{raw_url}{'&' if '?' in raw_url else '?'}{pairs}"

    body = None
    if request.body is not None:
        headers = [{"key": "Content-Type", "value": "application/json"}]
        body = {"mode": "raw", "raw": json.dumps(request.body)}
    elif request.form is not None:
        fields = [{"key": k, "value": v} for k, v in request.form.items()]
        if request.surface:
            fields.append({"key": "csrfmiddlewaretoken", "value": "{{csrfToken}}"})
        body = {"mode": "urlencoded", "urlencoded": fields}

    item = {
        "name": request.name,
        "request": {"method": method, "header": headers, "url": _url_for(raw_url)},
        "event": [
            {
                "listen": "test",
                "script": {"type": "text/javascript", "exec": _script_for(request, citation)},
            }
        ],
    }
    if body:
        item["request"]["body"] = body
    return item


def _default_item(operation: dict, statuses: list[str]) -> dict:
    citation = f"no check cites a requirement for {operation['method']} {operation['path']}"
    codes = [int(s) for s in statuses if s.isdigit()] or [200]
    return {
        "name": f"{operation['method']} {operation['path']} (default status check)",
        "request": {
            "method": operation["method"],
            "header": [],
            "url": _url_for("{{baseUrl}}" + operation["path"]),
        },
        "event": [
            {
                "listen": "test",
                "script": {
                    "type": "text/javascript",
                    "exec": [
                        f"pm.test({_js(citation + ' :: status is one the description documents')},"
                        " function () {",
                        f"  pm.expect({_js(codes)}).to.include(pm.response.code);",
                        "});",
                    ],
                },
            }
        ],
    }


def build(schema_path: Path, checks_root: Path, surfaces_path: Path, specs_root: Path) -> dict:
    schema = openapi.load(schema_path)
    operations = openapi.operations(schema)
    by_id = {op["operation_id"]: op for op in operations}
    capabilities = specs.load(specs_root)
    checks = library_module.load(checks_root, capabilities)
    declared = surfaces.load(surfaces_path)

    items = []
    used_operations = set()
    for check in checks:
        folder = {"name": check.citation, "item": []}
        for request in check.sequence:
            if request.operation:
                used_operations.add(request.operation)
                check_body_fields(schema, by_id, check.citation, request)
            if request.surface and request.surface["method"].upper() == "POST" and request.form:
                path = request.surface["path"]
                for pname, pvalue in request.path_params.items():
                    path = DJANGO_PARAM.sub(
                        lambda m: pvalue if m.group(1) == pname else m.group(0), path
                    )
                folder["item"].append(
                    _form_fetch_item(
                        "{{baseUrl}}" + path, f"fetch the form before: {request.name}"
                    )
                )
            folder["item"].append(_item(request, check.citation, by_id))
        items.append(folder)

    unchecked = [op for op in operations if op["operation_id"] not in used_operations]
    templated = [op for op in unchecked if "{" in op["path"]]
    if templated:
        # A default request cannot invent a path parameter. Left to synthesise
        # one it would request the template verbatim, be answered 404, and fail
        # as though the endpoint misbehaved. Failing here instead says what is
        # actually needed.
        listed = ", ".join(f"{op['method']} {op['path']}" for op in templated)
        raise ValueError(
            f"these operations take a path parameter and no check refers to them: {listed}. "
            "A default status check cannot supply the parameter, so each needs a check in "
            "checks/ that provides one."
        )
    if unchecked:
        folder = {"name": "Operations no check refers to", "item": []}
        for operation in unchecked:
            path_item = schema["paths"][operation["path"]][operation["method"].lower()]
            folder["item"].append(_default_item(operation, list(path_item.get("responses") or {})))
        items.append(folder)

    # Request names are not unique - "create the account" opens 35 different
    # sequences - so anything mapping a result back to its check by name would
    # attribute it to whichever check happened to be built last. A stable id per
    # item makes that mapping exact.
    for folder_index, folder in enumerate(items):
        for item_index, item in enumerate(folder["item"]):
            item["id"] = f"check-{folder_index:03d}-{item_index:03d}"

    return {
        "info": {
            "name": "API behaviour verification",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
        "variable": [
            {"key": "baseUrl", "value": "http://127.0.0.1:8000"},
            {"key": "mailBaseUrl", "value": "http://127.0.0.1:8025"},
            {"key": "runToken", "value": "local"},
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=HERE / "build" / "schema.yaml")
    parser.add_argument("--checks", type=Path, default=HERE / "checks")
    parser.add_argument("--surfaces", type=Path, default=HERE / "surfaces.yaml")
    parser.add_argument("--specs", type=Path, default=HERE.parent.parent / "openspec" / "specs")
    parser.add_argument("--out", type=Path, default=HERE / "build" / "collection.json")
    args = parser.parse_args(argv)

    collection = build(args.schema, args.checks, args.surfaces, args.specs)
    args.out.write_text(json.dumps(collection, indent=2) + "\n")
    folders = len(collection["item"])
    requests = sum(len(f["item"]) for f in collection["item"])
    print(f"Built {args.out} - {folders} folders, {requests} requests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
