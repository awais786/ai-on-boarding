"""Validation: run the project's own tests once the agent has finished.

The harness deliberately shells out to the same suite a developer runs, so a
harness verdict and a local `make test` cannot disagree.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

DJANGO_PROJECT = "sdd_django_demo"


@dataclass
class ValidationResult:
    ok: bool
    summary: str


def project_paths(repo_root: str) -> tuple[str, str]:
    """Absolute (project_dir, interpreter). Absolute because the interpreter is
    resolved against the subprocess's cwd, not ours — a relative repo_root
    would otherwise be looked up from inside the project directory."""
    project = os.path.join(os.path.abspath(repo_root), DJANGO_PROJECT)
    return project, os.path.join(project, ".venv", "bin", "python")


def run_tests(repo_root: str, timeout: int = 600) -> ValidationResult:
    project, python = project_paths(repo_root)
    if not os.path.exists(python):
        return ValidationResult(False, f"no interpreter at {python}")

    proc = subprocess.run(
        [python, "-m", "pytest", "-q"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
    return ValidationResult(
        ok=proc.returncode == 0,
        summary=lines[-1] if lines else "test run produced no output",
    )
