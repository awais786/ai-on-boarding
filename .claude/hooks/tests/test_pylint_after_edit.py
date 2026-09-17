"""Tests for the PostToolUse Pylint hook, covering Python and non-Python edits."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import pylint_after_edit as hook

HOOK = Path(__file__).resolve().parents[1] / "pylint_after_edit.py"
PROJECT_DIR = Path(__file__).resolve().parents[3]

# Missing module docstring, unused import, and a badly named constant: enough for
# Pylint to have something to say about a file that is nonetheless valid Python.
DIRTY_PYTHON = "import os\n\n\ndef F(x):\n    return x\n"
CLEAN_PYTHON = (
    '"""A tidy module."""\n\n\ndef add(left, right):\n'
    '    """Add two numbers."""\n    return left + right\n'
)


def payload(path, tool_name="Write"):
    return {
        "tool_name": tool_name,
        "tool_input": {"file_path": str(path), "content": "..."},
        "tool_response": {"filePath": str(path)},
    }


def pylint_available():
    return hook.resolve_pylint(str(PROJECT_DIR)) is not None


requires_pylint = pytest.mark.skipif(
    not pylint_available(), reason="pylint is not installed in this environment"
)


# --- file type detection ---------------------------------------------------------


@pytest.mark.parametrize("path", ["a.py", "pkg/mod.py", "stub.pyi", "A.PY"])
def test_recognises_python_files(path):
    assert hook.is_python_file(path)


@pytest.mark.parametrize(
    "path", ["README.md", "settings.json", "styles.css", "script.js", "data.pyc", None]
)
def test_rejects_non_python_files(path):
    assert not hook.is_python_file(path)


# --- non-Python edits are ignored entirely ---------------------------------------


@pytest.mark.parametrize("name", ["README.md", "config.json", "app.js", "notes.txt"])
def test_non_python_edit_produces_no_output(tmp_path, name):
    target = tmp_path / name
    target.write_text("some content\n")
    assert hook.decide(payload(target), str(tmp_path)) is None


def test_non_python_edit_does_not_invoke_pylint(tmp_path, monkeypatch):
    """Guards the requirement directly: Pylint must not run for a non-Python file."""
    calls = []
    monkeypatch.setattr(hook, "run_pylint", lambda *a, **k: calls.append(a) or (0, ""))
    target = tmp_path / "README.md"
    target.write_text("# Title\n")
    hook.decide(payload(target), str(tmp_path))
    assert not calls


# --- Python edits are linted and the report is fed back --------------------------


@requires_pylint
def test_python_edit_feeds_pylint_output_back_to_claude(tmp_path):
    target = tmp_path / "dirty.py"
    target.write_text(DIRTY_PYTHON)

    output = hook.decide(payload(target), str(tmp_path))

    assert output is not None, "a file with lint problems should produce feedback"
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "PostToolUse"
    context = specific["additionalContext"]
    assert "dirty.py" in context
    # Pylint emits message ids like C0114 / W0611; at least one must reach Claude.
    assert any(code in context for code in ("C0114", "W0611", "C0103"))


@requires_pylint
def test_clean_python_file_produces_no_noise(tmp_path):
    target = tmp_path / "clean.py"
    target.write_text(CLEAN_PYTHON)
    assert hook.decide(payload(target), str(tmp_path)) is None


@requires_pylint
def test_python_edit_via_bare_tool_input(tmp_path):
    """Some tools report only tool_input.file_path, with no tool_response."""
    target = tmp_path / "dirty.py"
    target.write_text(DIRTY_PYTHON)
    bare = {"tool_name": "Edit", "tool_input": {"file_path": str(target)}}
    assert hook.decide(bare, str(tmp_path)) is not None


# --- degraded environments --------------------------------------------------------


def test_missing_file_is_skipped(tmp_path):
    assert hook.decide(payload(tmp_path / "gone.py"), str(tmp_path)) is None


def test_absent_pylint_reports_instead_of_failing(tmp_path, monkeypatch):
    monkeypatch.setattr(hook, "resolve_pylint", lambda _project_dir: None)
    target = tmp_path / "mod.py"
    target.write_text(CLEAN_PYTHON)
    output = hook.decide(payload(target), str(tmp_path))
    assert "pylint is not installed" in output["systemMessage"]
    assert "hookSpecificOutput" not in output


def test_pylint_timeout_is_reported(tmp_path, monkeypatch):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="pylint", timeout=hook.TIMEOUT_SECONDS)

    monkeypatch.setattr(hook, "resolve_pylint", lambda _p: ["pylint"])
    monkeypatch.setattr(hook, "run_pylint", timeout)
    target = tmp_path / "mod.py"
    target.write_text(CLEAN_PYTHON)
    output = hook.decide(payload(target), str(tmp_path))
    assert "timed out" in output["systemMessage"]


def test_pylint_usage_error_is_reported_not_fed_back():
    output = hook.build_output("mod.py", hook.PYLINT_USAGE_ERROR, "bad option")
    assert "could not analyse" in output["systemMessage"]
    assert "hookSpecificOutput" not in output


# --- end to end, the way Claude Code actually invokes it --------------------------


def run_hook(data, cwd):
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        cwd=cwd,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(PROJECT_DIR)},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@requires_pylint
def test_end_to_end_python_file_returns_context(tmp_path):
    target = tmp_path / "dirty.py"
    target.write_text(DIRTY_PYTHON)
    stdout = run_hook(payload(target), cwd=str(tmp_path))
    assert json.loads(stdout)["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


def test_end_to_end_non_python_file_is_silent(tmp_path):
    target = tmp_path / "README.md"
    target.write_text("# Title\n")
    assert run_hook(payload(target), cwd=str(tmp_path)) == ""


# --- finding the virtualenv when it is not at the repository root ----------------


def test_pylint_is_found_in_a_subdirectory_venv(tmp_path, monkeypatch):
    """Regression: this repo keeps its venv in the Django subproject, not the root."""
    monkeypatch.delenv("PYLINT", raising=False)
    monkeypatch.setattr(hook.shutil, "which", lambda _name: None)
    nested = tmp_path / "myproject" / ".venv" / "bin"
    nested.mkdir(parents=True)
    fake = nested / "pylint"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)

    assert hook.resolve_pylint(str(tmp_path)) == [str(fake)]


def test_a_root_venv_still_wins_over_a_nested_one(tmp_path, monkeypatch):
    monkeypatch.delenv("PYLINT", raising=False)
    for location in (tmp_path, tmp_path / "myproject"):
        binaries = location / ".venv" / "bin"
        binaries.mkdir(parents=True)
        (binaries / "pylint").write_text("#!/bin/sh\nexit 0\n")
        (binaries / "pylint").chmod(0o755)

    assert hook.resolve_pylint(str(tmp_path)) == [str(tmp_path / ".venv" / "bin" / "pylint")]
