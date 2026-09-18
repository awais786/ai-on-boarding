"""Tests for run-pylint.py, the PostToolUse hook that lints a Python file Claude just
modified and feeds pylint's findings back via additionalContext.

Runs the hook as a real subprocess (stdin JSON in, stdout JSON out), same as
test_protect_sensitive_files.py, and against real files on disk since the hook reads
the target file itself rather than trusting tool_input's content.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent.parent / "run_pylint.py"
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DIRTY_PYTHON = "import os\n\ndef f():\n    x = 1\n    return 2\n"
CLEAN_PYTHON = '"""A trivially clean module."""\n'


def run_hook(payload, cwd=None):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(PROJECT_ROOT)
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        cwd=cwd,
        env=env,
    )


def write_payload(tool_name, file_path):
    return {"tool_name": tool_name, "tool_input": {"file_path": str(file_path)}}


def assert_no_output(result):
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def assert_additional_context_contains(result, *substrings):
    assert result.returncode == 0
    output = json.loads(result.stdout)
    hook_output = output["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PostToolUse"
    context = hook_output["additionalContext"]
    for substring in substrings:
        assert substring in context


def test_lints_a_python_file_with_issues(tmp_path):
    target = tmp_path / "dirty.py"
    target.write_text(DIRTY_PYTHON)

    result = run_hook(write_payload("Write", target))

    assert_additional_context_contains(result, str(target), "pylint findings")


def test_edit_tool_also_triggers_linting(tmp_path):
    target = tmp_path / "dirty_edit.py"
    target.write_text(DIRTY_PYTHON)

    result = run_hook(write_payload("Edit", target))

    assert_additional_context_contains(result, str(target))


def test_clean_python_file_produces_no_output(tmp_path):
    target = tmp_path / "clean.py"
    target.write_text(CLEAN_PYTHON)

    result = run_hook(write_payload("Write", target))

    assert_no_output(result)


def test_ignores_non_python_files(tmp_path):
    target = tmp_path / "notes.md"
    target.write_text("# Not Python\n\nSome text pylint would choke on if run: def(:\n")

    result = run_hook(write_payload("Write", target))

    assert_no_output(result)


def test_ignores_non_python_files_even_with_python_like_content(tmp_path):
    target = tmp_path / "snippet.txt"
    target.write_text(DIRTY_PYTHON)

    result = run_hook(write_payload("Write", target))

    assert_no_output(result)


def test_ignores_non_file_tools():
    result = run_hook({"tool_name": "Bash", "tool_input": {"command": "python3 x.py"}})
    assert_no_output(result)


def test_ignores_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.py"

    result = run_hook(write_payload("Write", missing))

    assert_no_output(result)


def test_fails_open_on_malformed_json():
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(PROJECT_ROOT)
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input="not valid json{{{",
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=env,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_truncates_very_long_pylint_output(tmp_path):
    # A file with one lint-triggering statement per line, well past the truncation
    # threshold, so the hook's line cap actually has to do something.
    lines = [f"x{i} = {i}" for i in range(200)]
    target = tmp_path / "many_issues.py"
    target.write_text("\n".join(lines) + "\n")

    result = run_hook(write_payload("Write", target))

    assert result.returncode == 0
    output = json.loads(result.stdout)
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "truncated" in context
