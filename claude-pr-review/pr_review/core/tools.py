"""Read-only tools given to the judge and verify agents. No write access, no
arbitrary shell - these three functions are the only ones ever wired into
the tool loop, so the guardrail is structural, not a prompt instruction.
"""
from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path

from pr_review.core.target import REPO_ROOT

MAX_OUTPUT_CHARS = 20_000
SEARCH_TIMEOUT_SECONDS = 30

# Skipped at traversal time (not filtered after) so list_files/grep don't
# do needless work walking these large, irrelevant directories.
SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


class ToolError(RuntimeError):
    """A tool call that failed, as opposed to one that succeeded with an
    empty result. execute() turns this into `is_error: true` so the model
    can tell "the call failed" from "the answer is nothing".
    """


def _resolve_within_repo(path: str) -> Path:
    """Resolve `path` to an absolute path and confirm it stays inside
    REPO_ROOT - rejects `..` traversal, absolute paths outside the repo, and
    symlinks that escape it. `path` is untrusted model output.
    """
    candidate = (REPO_ROOT / path).resolve()
    if not candidate.is_relative_to(REPO_ROOT):
        raise ToolError(f"path {path!r} resolves outside the repository")
    return candidate


def read_file(path: str) -> str:
    target = _resolve_within_repo(path)
    if not target.is_file():
        raise ToolError(f"No such file: {path}")
    content = target.read_text(errors="replace")
    if len(content) > MAX_OUTPUT_CHARS:
        content = content[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
    return content


def grep(pattern: str, path: str = ".") -> str:
    target = _resolve_within_repo(path)
    # Same exclusions list_files applies. Without them a search walks .venv,
    # .git and __pycache__ - burning the output budget on vendored code and
    # reporting "Binary file ... matches" hits the model can't act on.
    rg_excludes = [arg for d in SKIP_DIRS for arg in ("--glob", f"!{d}/")]
    grep_excludes = [f"--exclude-dir={d}" for d in SKIP_DIRS]

    try:
        # `--` stops rg from parsing `pattern` as flags - pattern is untrusted
        # model output, and a value like `--hidden` would otherwise be read as
        # an option rather than searched for.
        result = subprocess.run(
            ["rg", "--line-number", "--no-heading", *rg_excludes, "--", pattern, str(target)],
            capture_output=True, text=True, timeout=SEARCH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        result = None
    except subprocess.TimeoutExpired:
        raise ToolError("Search failed: timed out") from None

    if result is None or result.returncode not in (0, 1):  # 1 = no matches, not an error
        try:  # rg missing or errored oddly - fall back to grep
            result = subprocess.run(
                ["grep", "-rnI", "-E", *grep_excludes, "--", pattern, str(target)],
                capture_output=True, text=True, timeout=SEARCH_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            raise ToolError("Search failed: neither `rg` nor `grep` is available") from None
        except subprocess.TimeoutExpired:
            raise ToolError("Search failed: timed out") from None
        if result.returncode not in (0, 1):
            raise ToolError(f"Search failed: {result.stderr.strip()}")

    output = result.stdout.replace(str(REPO_ROOT) + "/", "")
    if not output.strip():
        return "No matches."
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
    return output


def list_files(directory: str = ".", pattern: str = "*") -> str:
    target = _resolve_within_repo(directory)
    if not target.is_dir():
        raise ToolError(f"No such directory: {directory}")

    matches = []
    for root, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not fnmatch.fnmatch(name, pattern):
                continue
            try:
                matches.append(str((Path(root) / name).relative_to(REPO_ROOT)))
            except ValueError:
                continue  # a symlink walked outside REPO_ROOT - skip it, don't crash the tool
    matches.sort()
    if not matches:
        return "No files matched."
    output = "\n".join(matches)
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + "\n... (truncated)"
    return output


TOOLS = [
    {
        "name": "read_file",
        "strict": True,
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
        "strict": True,
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
        "strict": True,
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


def execute(name: str, tool_input: dict) -> tuple[str, bool]:
    """Run a tool call. Returns (content, is_error).

    is_error matters: "No such file: x.py" returned as ordinary content
    reads to the model as fact rather than a failed call, and a verifier
    that believes a file is missing drops findings for that reason alone.

    "No matches."/"No files matched." are results, not errors - the search
    ran and the answer is empty.
    """
    handler = DISPATCH.get(name)
    if handler is None:
        return f"Unknown tool: {name}", True
    try:
        return handler(**tool_input), False
    except ToolError as exc:
        return str(exc), True
    except TypeError as exc:
        # Unreachable while every tool declares strict: true (the API
        # validates arguments against the schema before they reach us), but
        # a schema edit that drops strict shouldn't crash the run.
        return f"Bad arguments for {name}: {exc}", True
