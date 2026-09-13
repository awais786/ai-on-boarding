"""Resolve "what am I reviewing" the same way for every layer: a PR number,
a branch name, or nothing (the working tree's uncommitted changes).

Two roots, since a fork PR's tree is untrusted content:
- REPO_ROOT: the tree under review. Nothing in it is ever executed; the
  diff is wrapped in <untrusted_diff> markers before any model sees it.
- RULES_ROOT: where conventions (CLAUDE.md etc.) are read from - must stay
  TRUSTED, or a PR could rewrite the rules it's judged against.

Both default to this repo, so a local or same-repo-PR run is unaffected.
"""
from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parents[3]  # repo root, not claude-pr-review
REPO_ROOT = Path(os.environ.get("PR_REVIEW_REPO_ROOT") or _DEFAULT_ROOT).resolve()
RULES_ROOT = Path(os.environ.get("PR_REVIEW_RULES_ROOT") or REPO_ROOT).resolve()

# File types dropped from the diff before any model sees it. Every excluded
# file is input tokens paid for on every call of every layer, and Layer 1
# cannot lint prose anyway. Comma-separated globs matched against the whole
# path, so "*.md" covers "docs/a.md". Set the variable to empty to review
# everything.
#
# This filters the DIFF only. The rules a PR is judged against (CLAUDE.md,
# openspec/config.yaml) are read from RULES_ROOT by repo_rules() and are
# never affected by what is excluded here.
EXCLUDE_GLOBS = [
    g.strip()
    for g in os.environ.get("PR_REVIEW_EXCLUDE_GLOBS", "*.md").split(",")
    if g.strip()
]

_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)$", re.M)
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


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
    """Convention documents, keyed by path - the citable source for judge
    and verify. Read from RULES_ROOT, never REPO_ROOT (see module docstring).
    """
    paths = ["CLAUDE.md", "openspec/config.yaml", "sdd_django_demo/CLAUDE.md"]
    return {
        p: (RULES_ROOT / p).read_text() if (RULES_ROOT / p).exists() else ""
        for p in paths
    }


def changed_lines(diff: str) -> dict[str, set[int]]:
    """Path -> the set of line numbers this diff ADDS or MODIFIES, numbered
    in the new file. Used to scope Layer 1 to what the PR actually wrote.

    A modified line appears as a removal plus an addition, so the added-line
    set covers edits as well as pure insertions. Removed lines don't exist
    in the new file and so have no number to report against.
    """
    out: dict[str, set[int]] = {}
    path: str | None = None
    new_line = 0
    for line in diff.splitlines():
        header = _DIFF_HEADER_RE.match(line)
        if header:
            path = header.group(2)
            out.setdefault(path, set())
            continue
        hunk = _HUNK_RE.match(line)
        if hunk:
            new_line = int(hunk.group(1))
            continue
        if path is None or line.startswith(("---", "+++")):
            continue
        if line.startswith("+"):
            out[path].add(new_line)
            new_line += 1
        elif line.startswith("-"):
            continue  # gone from the new file, so it has no new-file line
        elif line.startswith(" ") or not line:
            new_line += 1
    return out


def is_excluded(path: str) -> bool:
    return any(fnmatch.fnmatch(path, glob) for glob in EXCLUDE_GLOBS)


def filter_diff(diff: str) -> str:
    """Drop whole per-file sections whose paths all match EXCLUDE_GLOBS.

    Fails open: a section whose header doesn't parse is kept, because
    silently dropping a source file from the review is far worse than
    reviewing a doc nobody asked for.
    """
    if not EXCLUDE_GLOBS or not diff:
        return diff
    sections = re.split(r"^(?=diff --git )", diff, flags=re.M)
    kept = []
    for section in sections:
        header = _DIFF_HEADER_RE.match(section)
        paths = [header.group(1), header.group(2)] if header else []
        if paths and all(is_excluded(p) for p in paths):
            continue
        kept.append(section)
    return "".join(kept)


def get_diff(target: str | None) -> str:
    """The unified diff for the target - every changed file, not just `.py`
    ones, since the judge/verify agents review the whole PR. File types in
    EXCLUDE_GLOBS are dropped here, so every layer sees the same diff.
    """
    if target and target.isdigit():
        return filter_diff(_run("gh", "pr", "diff", target))
    if target:
        base = _run("git", "merge-base", _default_branch(), target).strip()
        return filter_diff(_run("git", "diff", f"{base}...{target}"))
    return filter_diff(_run("git", "diff") + _run("git", "diff", "--staged"))
