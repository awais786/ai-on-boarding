"""Deterministic clone + write-lockdown for the target repo under
discovery. This is plain Python, not the agent's own tool call - cloning a
repo has exactly one correct way to do it, so there's no judgment for the
model to add. Doing it before the agent session starts means the lockdown
below is airtight: the agent's session never sees the directory in a
writable state, independent of which tools it's later granted.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Callable

Runner = Callable[[list[str]], None]


def _default_runner(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def clone_repo(url: str, dest: Path, *, runner: Runner = _default_runner) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    runner(["git", "clone", "--depth", "1", url, str(dest)])


def lock_down(path: Path) -> None:
    """Strips write permission from every file and directory under path,
    bottom-up (files and subdirectories before their parent, so a parent's
    write bit isn't removed before its children are reachable).
    """
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            _strip_write(Path(root) / name)
        for name in dirs:
            _strip_write(Path(root) / name)
    _strip_write(path)


def _strip_write(target: Path) -> None:
    if target.is_symlink():
        return  # chmod/stat would follow the link; never touch anything outside the walked tree
    current_mode = target.stat().st_mode
    target.chmod(current_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
