"""Layer 1 reports only on lines the PR actually wrote.

ruff lints each changed file WHOLE, so before this a PR that touched one
line of a file inherited every pre-existing violation in it. A live run
blocked a PR on a B904 forty lines above anything it changed - the author's
only route to merging was fixing unrelated code they never touched.
"""
from __future__ import annotations

from pr_review.core import target
from pr_review.pipeline import lint

DIFF = """diff --git a/app/views.py b/app/views.py
index 111..222 100644
--- a/app/views.py
+++ b/app/views.py
@@ -10,3 +10,5 @@ def existing():
     untouched_context()
     also_untouched()
+    brand_new_line()
+    another_new_line()
     trailing_context()
"""


def test_changed_lines_finds_only_added_lines():
    assert target.changed_lines(DIFF) == {"app/views.py": {12, 13}}


def test_a_finding_on_an_added_line_is_kept():
    result = {"status": "fail", "findings": [
        {"file": "app/views.py", "line": 12, "code": "F401", "message": "unused"},
    ]}
    out = lint.scope_to_changed_lines(result, target.changed_lines(DIFF))
    assert len(out["findings"]) == 1
    assert out["status"] == "fail"


def test_a_finding_on_an_untouched_line_is_dropped():
    result = {"status": "fail", "findings": [
        {"file": "app/views.py", "line": 10, "code": "B904", "message": "pre-existing"},
    ]}
    out = lint.scope_to_changed_lines(result, target.changed_lines(DIFF))
    assert out["findings"] == []
    assert out["status"] == "pass", "a PR with only inherited debt must not fail Layer 1"


def test_a_file_the_diff_says_nothing_about_keeps_its_findings():
    # Fails SAFE: absent from the map means "the diff told us nothing",
    # not "nothing changed". Dropping these would silently switch Layer 1
    # off whenever diff parsing failed, and a review that reports nothing
    # looks exactly like a clean one.
    result = {"status": "fail", "findings": [
        {"file": "other/module.py", "line": 12, "code": "F821", "message": "elsewhere"},
    ]}
    out = lint.scope_to_changed_lines(result, target.changed_lines(DIFF))
    assert len(out["findings"]) == 1


def test_an_unparseable_diff_disables_nothing():
    result = {"status": "fail", "findings": [
        {"file": "app/views.py", "line": 10, "code": "B904", "message": "x"},
    ]}
    assert len(lint.scope_to_changed_lines(result, target.changed_lines(""))["findings"]) == 1


def test_a_wholly_new_file_keeps_every_finding():
    new_file = (
        "diff --git a/app/new.py b/app/new.py\n"
        "--- /dev/null\n"
        "+++ b/app/new.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+import os\n"
        "+import sys\n"
        "+print(1)\n"
    )
    result = {"status": "fail", "findings": [
        {"file": "app/new.py", "line": 1, "code": "F401", "message": "unused"},
        {"file": "app/new.py", "line": 3, "code": "T201", "message": "print"},
    ]}
    out = lint.scope_to_changed_lines(result, target.changed_lines(new_file))
    assert len(out["findings"]) == 2


def test_a_modified_line_counts_as_changed():
    # A modified line shows up as a removal plus an addition, so the new
    # line number is in the added set and the finding survives.
    modified = (
        "diff --git a/app/x.py b/app/x.py\n"
        "--- a/app/x.py\n"
        "+++ b/app/x.py\n"
        "@@ -5,3 +5,3 @@\n"
        " context\n"
        "-password = 'old'\n"
        "+password = 'hunter2'\n"
        " trailing\n"
    )
    assert target.changed_lines(modified) == {"app/x.py": {6}}
    result = {"status": "fail", "findings": [
        {"file": "app/x.py", "line": 6, "code": "S105", "message": "hardcoded"},
    ]}
    assert len(lint.scope_to_changed_lines(result, target.changed_lines(modified))["findings"]) == 1


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"ok ({len(TESTS)} tests)")
