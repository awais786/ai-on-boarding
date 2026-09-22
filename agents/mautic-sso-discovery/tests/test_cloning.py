from __future__ import annotations

import os

import pytest

from mautic_sso_discovery.cloning import clone_repo, lock_down

pytestmark = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses file permission bits, making this test meaningless",
)


def test_clone_repo_invokes_git_clone_with_depth_1(tmp_path):
    calls = []
    dest = tmp_path / "target"

    clone_repo("https://example.com/some/repo.git", dest, runner=calls.append)

    assert calls == [["git", "clone", "--depth", "1", "https://example.com/some/repo.git", str(dest)]]


def test_lock_down_blocks_writes_to_existing_files(tmp_path):
    target = tmp_path / "cloned"
    nested_file = target / "sub" / "file.txt"
    nested_file.parent.mkdir(parents=True)
    nested_file.write_text("original")

    lock_down(target)

    with pytest.raises(PermissionError):
        nested_file.write_text("tampered")


def test_lock_down_blocks_new_file_creation(tmp_path):
    target = tmp_path / "cloned"
    target.mkdir()
    (target / "existing.txt").write_text("x")

    lock_down(target)

    with pytest.raises(PermissionError):
        (target / "new.txt").write_text("nope")
