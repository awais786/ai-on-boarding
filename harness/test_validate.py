"""Tests for the verification layer.

These avoid running the project's real checks (~35s for the suite); they cover
the path handling and the pass/fail reading that decide the verdict.
"""
from __future__ import annotations

import os

from harness.validate import Check, resolve, run_check, run_checks


def test_relative_interpreter_is_made_absolute():
    """Regression: a relative path once resolved against the subprocess's cwd,
    so the interpreter was looked up from inside the project directory."""
    check = Check(name="tests", command=[".venv/bin/python"], cwd="sdd_django_demo")

    cwd, command = resolve(".", check)

    assert os.path.isabs(cwd)
    assert os.path.isabs(command[0])
    assert command[0].endswith("sdd_django_demo/.venv/bin/python")


def test_command_on_the_path_is_left_alone():
    cwd, command = resolve(".", Check(name="specs", command=["openspec", "validate"]))

    assert command == ["openspec", "validate"]
    assert os.path.isabs(cwd)


def test_failing_command_is_reported_as_failing():
    result = run_check(".", Check(name="nope", command=["sh", "-c", "exit 3"]))

    assert result.ok is False


def test_passing_command_keeps_its_last_line_as_the_summary():
    result = run_check(".", Check(name="yes", command=["sh", "-c", "echo all good"]))

    assert result.ok is True
    assert result.summary == "all good"


def test_missing_command_reports_instead_of_raising():
    result = run_check(".", Check(name="ghost", command=["definitely-not-a-command"]))

    assert result.ok is False
    assert "not found" in result.summary


def test_missing_directory_reports_instead_of_raising():
    result = run_check(".", Check(name="ghost", command=["true"], cwd="no/such/dir"))

    assert result.ok is False
    assert "no such directory" in result.summary


def test_every_check_runs_and_each_gets_a_result():
    checks = [
        Check(name="a", command=["sh", "-c", "exit 0"]),
        Check(name="b", command=["sh", "-c", "exit 1"]),
        Check(name="c", command=["sh", "-c", "exit 0"]),
    ]

    results = run_checks(".", checks)

    assert [r.name for r in results] == ["a", "b", "c"]
    assert [r.ok for r in results] == [True, False, True]
