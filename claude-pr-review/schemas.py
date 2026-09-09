"""The one output shape both the judge and verify agents are constrained to
via `output_config.format` - enforced by the API itself (structured
outputs), not by asking the model nicely to skip prose and markdown fences.
"""

FINDING = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": ["CRITICAL", "MAJOR", "MINOR"]},
        "summary": {"type": "string"},
        "citation": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "The exact requirement, named failing test, or quoted convention text this finding is based on, or null if none applies.",
        },
        "file": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "line": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
    },
    "required": ["severity", "summary", "citation", "file", "line"],
    "additionalProperties": False,
}

FINDINGS_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {"findings": {"type": "array", "items": FINDING}},
        "required": ["findings"],
        "additionalProperties": False,
    },
}
