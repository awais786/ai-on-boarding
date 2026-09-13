"""target.filter_diff(): dropping file types nobody needs reviewed.

Every excluded file is input tokens paid for on every call of every layer,
so this is a cost lever as much as a noise one. It is also the one place a
mistake silently removes a source file from review entirely, which is why
the parser fails open.
"""
from __future__ import annotations

from pr_review.core import target


def _section(path: str, body: str = "+hello\n") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"index 111..222 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1 @@\n{body}"
    )


def _with_globs(globs, diff):
    original = target.EXCLUDE_GLOBS
    target.EXCLUDE_GLOBS = globs
    try:
        return target.filter_diff(diff)
    finally:
        target.EXCLUDE_GLOBS = original


def test_markdown_is_dropped_and_source_is_kept():
    diff = _section("README.md") + _section("app/views.py")
    out = _with_globs(["*.md"], diff)
    assert "README.md" not in out
    assert "app/views.py" in out


def test_a_glob_matches_anywhere_in_the_path():
    diff = _section("docs/deep/nested/guide.md")
    assert _with_globs(["*.md"], diff) == ""


def test_several_globs_are_honoured():
    diff = _section("a.md") + _section("b.txt") + _section("c.py")
    out = _with_globs(["*.md", "*.txt"], diff)
    assert "a.md" not in out
    assert "b.txt" not in out
    assert "c.py" in out


def test_empty_glob_list_reviews_everything():
    diff = _section("README.md") + _section("app/views.py")
    assert _with_globs([], diff) == diff


def test_an_unparseable_section_is_kept():
    # Fails open: silently dropping a source file from the review is far
    # worse than reviewing a doc nobody asked for.
    weird = "diff --cc some/merge/file.py\n@@@ -1 +1 @@@\n+x\n"
    assert _with_globs(["*.md"], weird) == weird


def test_a_rename_from_source_to_doc_is_kept():
    # Only one of the two paths is excluded, so the change still gets
    # reviewed - deleting code into a .md file is exactly what review is for.
    diff = (
        "diff --git a/app/views.py b/docs/views.md\n"
        "similarity index 80%\n"
        "rename from app/views.py\n"
        "rename to docs/views.md\n"
    )
    assert _with_globs(["*.md"], diff) == diff


def test_preamble_before_the_first_section_survives():
    diff = _section("app/views.py")
    assert _with_globs(["*.md"], diff) == diff


def test_the_default_excludes_markdown():
    assert target.is_excluded("CLAUDE.md") is True
    assert target.is_excluded("app/views.py") is False


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"ok ({len(TESTS)} tests)")
