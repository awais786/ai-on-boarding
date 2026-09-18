#!/usr/bin/env python3
"""PostToolUse hook: run pylint on a Python file Claude just modified, and feed the
report back to Claude via additionalContext so it can fix what pylint flags.

Only fires for Write/Edit calls whose target file ends in `.py`. Non-Python files are
left alone entirely - pylint is never invoked and nothing is printed.
"""
import json
import os
import shutil
import subprocess

from _hook_common import file_path_for, read_payload

FILE_TOOLS = {"Write", "Edit"}
MAX_OUTPUT_LINES = 60


def find_pylint():
    """Return the pylint command to run, or None if it can't be found anywhere."""
    on_path = shutil.which("pylint")
    if on_path:
        return [on_path]
    # Fall back to this project's own virtualenv - pylint is a dev dependency of
    # sdd_django_demo, not necessarily on the ambient PATH the hook runs under.
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    candidate = os.path.join(project_dir, "sdd_django_demo", ".venv", "bin", "pylint")
    if os.path.isfile(candidate):
        return [candidate]
    return None


def run_pylint(pylint_cmd, file_path):
    """Run pylint against file_path and return its (possibly truncated) text output."""
    try:
        result = subprocess.run(
            pylint_cmd + ["--output-format=text", "--score=n", file_path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        return f"pylint could not be run: {err}"
    output = (result.stdout or "") + (result.stderr or "")
    lines = output.strip().splitlines()
    if not lines:
        return ""
    if len(lines) > MAX_OUTPUT_LINES:
        omitted = len(lines) - MAX_OUTPUT_LINES
        lines = lines[:MAX_OUTPUT_LINES] + [f"... ({omitted} more lines truncated)"]
    return "\n".join(lines)


def emit(context):
    """Print a PostToolUse additionalContext payload for Claude Code to pick up."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        },
    }))


def main():
    """Lint the just-modified file if it's Python, and surface findings to Claude."""
    payload = read_payload()
    if payload is None:
        return

    file_path = file_path_for(payload, FILE_TOOLS)
    if not file_path or not file_path.endswith(".py"):
        return

    if not os.path.isfile(file_path):
        return  # file was deleted/moved by the time the hook runs, or path is bogus

    pylint_cmd = find_pylint()
    if pylint_cmd is None:
        emit(
            f"pylint is not installed, so `{file_path}` was not linted after this "
            f"edit. Install it (e.g. `pip install pylint`) to enable this check."
        )
        return

    report = run_pylint(pylint_cmd, file_path)
    if not report:
        return  # clean file, nothing worth surfacing

    emit(f"pylint findings for `{file_path}` (fix what applies):\n\n{report}")


if __name__ == "__main__":
    main()
