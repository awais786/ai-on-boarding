#!/usr/bin/env python3
"""PostToolUse hook: run Pylint on a Python file Claude just edited.

Reads a PostToolUse hook payload on stdin. When the edited file is a Python file
that still exists on disk, Pylint runs against it and the report is handed back to
Claude as additional context so it can fix what was reported.

Non-Python files are ignored: the hook writes nothing and exits 0.

Pylint is located in this order, so the hook works whether or not a virtualenv is
active: $PYLINT, then .venv/bin/pylint beside the project, then pylint on PATH,
then `python -m pylint`. If none of those resolve, the hook reports that once as a
user-visible note rather than failing the edit.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PYTHON_SUFFIXES = {".py", ".pyi"}
TIMEOUT_SECONDS = 60

# Pylint exits non-zero to encode which message classes it emitted; only 32 means
# "pylint itself failed to run". See pylint's exit-code documentation.
PYLINT_USAGE_ERROR = 32


def is_python_file(path: str | None) -> bool:
    """True when the path names a Python source file."""
    if not path:
        return False
    return Path(path).suffix.lower() in PYTHON_SUFFIXES


def edited_path(payload: dict) -> str | None:
    """Return the file this tool call wrote, or None if it did not write one."""
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    tool_response = payload.get("tool_response")
    tool_response = tool_response if isinstance(tool_response, dict) else {}

    for source, key in (
        (tool_response, "filePath"),
        (tool_input, "file_path"),
        (tool_input, "notebook_path"),
    ):
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def venv_candidates(root: Path):
    """Yield the pylint paths to try under ``root``, nearest first.

    A repository does not always keep its virtualenv at the top: here the Django
    project is a subdirectory and owns the venv, so looking only at the root found
    nothing. One level down is enough to cover that layout without walking the
    tree, and it avoids hard-coding an absolute path into shared configuration.
    """
    yield root / ".venv" / "bin" / "pylint"
    try:
        children = sorted(entry for entry in root.iterdir() if entry.is_dir())
    except OSError:
        return
    for child in children:
        if child.name.startswith("."):
            continue
        yield child / ".venv" / "bin" / "pylint"


def resolve_pylint(project_dir: str | None) -> list[str] | None:
    """Return the argv prefix that runs Pylint, or None when it is unavailable."""
    override = os.environ.get("PYLINT")
    if override:
        return [override]

    roots = [project_dir] if project_dir else []
    roots.append(os.getcwd())
    for root in roots:
        for candidate in venv_candidates(Path(root)):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return [str(candidate)]

    found = shutil.which("pylint")
    if found:
        return [found]

    try:
        subprocess.run(
            [sys.executable, "-m", "pylint", "--version"],
            capture_output=True,
            check=True,
            timeout=TIMEOUT_SECONDS,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return [sys.executable, "-m", "pylint"]


def run_pylint(argv: list[str], path: str, project_dir: str | None) -> tuple[int, str]:
    """Run Pylint against ``path`` and return its exit code and combined report."""
    completed = subprocess.run(
        [*argv, "--score=no", path],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        cwd=project_dir or None,
        check=False,
    )
    report = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, report.strip()


def build_output(path: str, returncode: int, report: str) -> dict | None:
    """Turn a Pylint result into the JSON this hook should emit, or None if clean."""
    if returncode == 0 and not report:
        return None
    if returncode & PYLINT_USAGE_ERROR:
        return {
            "systemMessage": f"pylint could not analyse {path}:\n{report}",
        }
    if not report:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"Pylint reported the following on {path}. Fix the issues that are real "
                f"defects or style violations for this project; if a message does not "
                f"apply, say so rather than silently ignoring it.\n\n{report}"
            ),
        }
    }


def decide(payload: dict, project_dir: str | None) -> dict | None:
    """Map a payload to the JSON this hook should emit, or None to stay silent."""
    path = edited_path(payload)
    if not is_python_file(path):
        return None
    assert path is not None
    resolved = path if os.path.isabs(path) else os.path.join(project_dir or "", path)
    if not os.path.isfile(resolved):
        return None

    argv = resolve_pylint(project_dir)
    if argv is None:
        return {
            "systemMessage": (
                "pylint is not installed, so the post-edit lint of "
                f"{path} was skipped. Install it with `pip install pylint`."
            )
        }

    try:
        returncode, report = run_pylint(argv, resolved, project_dir)
    except subprocess.TimeoutExpired:
        return {"systemMessage": f"pylint timed out after {TIMEOUT_SECONDS}s on {path}."}
    except OSError as exc:
        return {"systemMessage": f"pylint could not be run on {path}: {exc}"}

    return build_output(path, returncode, report)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    output = decide(payload, project_dir)
    if output is not None:
        json.dump(output, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
