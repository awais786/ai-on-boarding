"""Tests for the validation step.

These avoid running the Django suite itself (~35s); they cover the path
handling that decides whether the suite can be found at all.
"""
from __future__ import annotations

import os

from harness.validate import project_paths, run_tests


def test_paths_are_absolute_for_a_relative_repo_root():
    """Regression: a relative root once resolved the interpreter against the
    subprocess's cwd, so pytest was looked up inside sdd_django_demo/."""
    project, python = project_paths(".")

    assert os.path.isabs(project)
    assert os.path.isabs(python)


def test_relative_and_absolute_roots_agree():
    assert project_paths(".") == project_paths(os.path.abspath("."))


def test_missing_interpreter_reports_instead_of_raising(tmp_path):
    result = run_tests(str(tmp_path))

    assert result.ok is False
    assert "no interpreter" in result.summary
