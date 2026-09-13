"""Per-finding inline comments: a severity dot, a short body, posted once.

A single wall-of-text verdict comment is not something a reviewer reads.
Each finding now goes on the line it is about, and the summary comment
keeps the complete record so nothing is lost when a line falls outside the
diff and GitHub refuses the inline comment.
"""
from __future__ import annotations

from pr_review.ci import github, post
from pr_review.pipeline import gate


def _finding(fp="a1b2c3d4e5f6a1b2", severity="CRITICAL", file="app/x.py", line=7, **kw):
    f = {"fp": fp, "severity": severity, "file": file, "line": line,
         "summary": "MD5 is unsuitable for signing.", "citation": None}
    f.update(kw)
    return f


class _FakeGitHub:
    GitHubError = github.GitHubError

    def __init__(self, existing=None, fail_on=()):
        self.existing = existing or []
        self.fail_on = fail_on
        self.posted = []

    def pr_review_comments(self, repo, pr):
        return self.existing

    def create_review_comment(self, repo, pr, commit_sha, path, line, body):
        if path in self.fail_on:
            raise github.GitHubError(f"line {line} is outside the diff")
        self.posted.append({"path": path, "line": line, "body": body})


def _post(fake, findings):
    original = post.github
    post.github = fake
    try:
        return post.post_inline_comments("o/r", "1", "sha", findings)
    finally:
        post.github = original


def test_each_finding_gets_its_own_comment_with_a_severity_dot():
    fake = _FakeGitHub()
    count = _post(fake, [
        _finding(fp="aaaa1111aaaa1111", severity="CRITICAL", line=7),
        _finding(fp="bbbb2222bbbb2222", severity="MINOR", line=9),
    ])
    assert count == 2
    assert fake.posted[0]["body"].startswith("🔴 **CRITICAL**")
    assert fake.posted[1]["body"].startswith("🟡 **MINOR**")
    assert [c["line"] for c in fake.posted] == [7, 9]


def test_a_finding_already_commented_is_not_posted_again():
    fp = "aaaa1111aaaa1111"
    fake = _FakeGitHub(existing=[{"body": f"old text\n<!-- {post.FINDING_MARKER}:{fp} -->"}])
    assert _post(fake, [_finding(fp=fp)]) == 0


def test_a_finding_with_no_location_is_left_to_the_summary():
    fake = _FakeGitHub()
    assert _post(fake, [_finding(file=None, line=None)]) == 0


def test_dismissed_and_resolved_findings_are_not_commented():
    fake = _FakeGitHub()
    findings = [
        _finding(fp="aaaa1111aaaa1111", status="dismissed"),
        _finding(fp="bbbb2222bbbb2222", status="resolved"),
    ]
    assert _post(fake, findings) == 0


def test_a_rejected_line_does_not_break_the_run():
    # GitHub refuses comments on lines outside the diff. The summary is the
    # complete record, so this costs presentation, not information.
    fake = _FakeGitHub(fail_on=("app/x.py",))
    assert _post(fake, [_finding()]) == 0


def test_summary_lines_are_short_and_dotted():
    f = _finding(summary="x" * 400)
    line = gate._line(f)
    assert line.startswith("- 🔴 **CRITICAL**")
    assert len(line) < 300, "a summary line must stay skimmable"
    assert line.endswith("`app/x.py:7`")


def test_finding_comment_states_its_basis():
    verified = gate.render_finding_comment(_finding(verified=True))
    assert "Layer 3's independent verification" in verified
    cited = gate.render_finding_comment(_finding(citation="ruff:S324"))
    assert "cites: ruff:S324" in cited


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"ok ({len(TESTS)} tests)")
