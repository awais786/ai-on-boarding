"""Verification: run the project's own checks once the agent has finished.

Multi-layered on purpose — a passing test suite does not catch a broken Django
config or a spec that no longer validates. Each check is data in policy.yaml,
so adding a linter is a config edit rather than a code change.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field


@dataclass
class Check:
    name: str
    command: list[str] = field(default_factory=list)
    cwd: str = "."


@dataclass
class CheckResult:
    name: str
    ok: bool
    summary: str


def resolve(repo_root: str, check: Check) -> tuple[str, list[str]]:
    """Absolute cwd and command.

    The executable is resolved against the subprocess's cwd, not ours, so a
    relative interpreter path has to be expanded here or it is looked up from
    inside the wrong directory.
    """
    cwd = os.path.join(os.path.abspath(repo_root), check.cwd)
    command = list(check.command)
    if command:
        # isfile, not exists: the repo has an `openspec/` directory, and a
        # bare `openspec` command must still resolve to the CLI on PATH.
        local = os.path.join(cwd, command[0])
        if os.path.isfile(local) and os.access(local, os.X_OK):
            command[0] = local
    return cwd, command


def run_check(repo_root: str, check: Check, timeout: int = 900) -> CheckResult:
    cwd, command = resolve(repo_root, check)
    if not command:
        return CheckResult(check.name, False, "check defines no command")
    if not os.path.isdir(cwd):
        return CheckResult(check.name, False, f"no such directory: {cwd}")

    try:
        proc = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        return CheckResult(check.name, False, f"command not found: {command[0]}")
    except subprocess.TimeoutExpired:
        return CheckResult(check.name, False, f"timed out after {timeout}s")

    lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
    return CheckResult(
        name=check.name,
        ok=proc.returncode == 0,
        summary=lines[-1] if lines else "produced no output",
    )


def run_checks(repo_root: str, checks: list[Check]) -> list[CheckResult]:
    return [run_check(repo_root, check) for check in checks]
