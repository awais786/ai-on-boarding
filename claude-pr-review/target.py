"""Resolve "what am I reviewing" the same way for every layer: a PR number,
a branch name, or nothing (the working tree's uncommitted changes).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> str:
    result = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return result.stdout


def _default_branch() -> str:
    for candidate in ("origin/main", "main", "origin/master", "master"):
        check = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            cwd=REPO_ROOT, capture_output=True,
        )
        if check.returncode == 0:
            return candidate
    return "HEAD"


def changed_python_files(target: str | None) -> list[str]:
    """Every `.py` file the target touches, relative to REPO_ROOT."""
    if target and target.isdigit():
        names = _run("gh", "pr", "diff", target, "--name-only")
    elif target:
        base = _run("git", "merge-base", _default_branch(), target).strip()
        names = _run("git", "diff", "--name-only", f"{base}...{target}")
    else:
        names = _run("git", "diff", "--name-only") + _run("git", "diff", "--name-only", "--staged")

    files = sorted({line for line in names.splitlines() if line})
    return [f for f in files if f.endswith(".py") and (REPO_ROOT / f).exists()]


def repo_rules() -> dict[str, str]:
    """This repo's own convention documents, keyed by their path - the
    citable source for both the judge and verify agents.
    """
    paths = ["CLAUDE.md", "openspec/config.yaml", "sdd_django_demo/CLAUDE.md"]
    return {
        p: (REPO_ROOT / p).read_text() if (REPO_ROOT / p).exists() else ""
        for p in paths
    }


def get_diff(target: str | None) -> str:
    """The full unified diff for the target - every changed file, not just
    `.py` ones, since the judge/verify agents review the whole PR.
    """
    if target and target.isdigit():
        return _run("gh", "pr", "diff", target)
    if target:
        base = _run("git", "merge-base", _default_branch(), target).strip()
        return _run("git", "diff", f"{base}...{target}")
    return _run("git", "diff") + _run("git", "diff", "--staged")
