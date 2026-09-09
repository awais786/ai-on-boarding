"""Read-only tools given to both the judge and verify agents. No tool here
can write to the repository, run arbitrary shell commands, or leave the
repo root - the guardrail is structural (these are the only three functions
ever wired into the tool loop), not a prompt instruction the model could be
talked out of.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from target import REPO_ROOT

MAX_OUTPUT_CHARS = 20_000


def _resolve_within_repo(path: str) -> Path:
    """Resolve `path` to an absolute path and confirm it stays inside
    REPO_ROOT - rejects `..` traversal, absolute paths outside the repo, and
    symlinks that escape it. `path` is untrusted model output.
    """
    candidate = (REPO_ROOT / path).resolve()
    if not candidate.is_relative_to(REPO_ROOT):
        raise ValueError(f"path {path!r} resolves outside the repository")
    return candidate


def read_file(path: str) -> str:
    try:
        target = _resolve_within_repo(path)
    except ValueError as exc:
        return str(exc)
    if not target.is_file():
        return f"No such file: {path}"
    content = target.read_text(errors="replace")
    if len(content) > MAX_OUTPUT_CHARS:
        content = content[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
    return content


def grep(pattern: str, path: str = ".") -> str:
    try:
        target = _resolve_within_repo(path)
    except ValueError as exc:
        return str(exc)

    try:
        result = subprocess.run(
            ["rg", "--line-number", "--no-heading", pattern, str(target)],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        result = None

    if result is None or result.returncode not in (0, 1):  # 1 = no matches, not an error
        # Fall back to `grep` if ripgrep isn't installed (or errored oddly).
        try:
            result = subprocess.run(
                ["grep", "-rn", "-E", pattern, str(target)], capture_output=True, text=True,
            )
        except FileNotFoundError:
            return "Search failed: neither `rg` nor `grep` is available"
        if result.returncode not in (0, 1):
            return f"Search failed: {result.stderr.strip()}"

    output = result.stdout.replace(str(REPO_ROOT) + "/", "")
    if not output.strip():
        return "No matches."
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
    return output


def list_files(directory: str = ".", pattern: str = "*") -> str:
    try:
        target = _resolve_within_repo(directory)
    except ValueError as exc:
        return str(exc)
    if not target.is_dir():
        return f"No such directory: {directory}"

    matches = sorted(
        str(p.relative_to(REPO_ROOT)) for p in target.rglob(pattern)
        if p.is_file() and ".venv" not in p.parts and "__pycache__" not in p.parts
    )
    if not matches:
        return "No files matched."
    output = "\n".join(matches)
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
    return output


TOOLS = [
    {
        "name": "read_file",
        "description": "Read the full contents of a file in this repository. Call this to inspect existing code when checking for duplication or convention compliance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path relative to the repository root, e.g. sdd_django_demo/api/serializers.py",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "grep",
        "description": "Search the repository for a regex pattern. Use this to find similarly-named functions or duplicated logic elsewhere in the codebase before raising a blast-radius finding.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {
                    "type": "string",
                    "description": "Directory or file to search under, relative to the repo root. Defaults to the whole repository.",
                },
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_files",
        "description": "List files under a directory in this repository, optionally filtered by a glob pattern (e.g. '*.py'). Use this to explore repo structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory relative to the repo root. Defaults to the repo root.",
                },
                "pattern": {"type": "string", "description": "Glob pattern. Defaults to every file."},
            },
            "required": [],
            "additionalProperties": False,
        },
    },
]

DISPATCH = {"read_file": read_file, "grep": grep, "list_files": list_files}


def execute(name: str, tool_input: dict) -> str:
    handler = DISPATCH.get(name)
    if handler is None:
        return f"Unknown tool: {name}"
    try:
        return handler(**tool_input)
    except TypeError as exc:
        return f"Bad arguments for {name}: {exc}"
