"""Tests for review.diff, written from the pr-review spec.

- "Post each finding as its own isolated comment" (the inline case) and "Fall back to
  a general comment for unattachable findings" both depend on correctly telling which
  (file, line) positions a pull request's diff actually makes available.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

import pytest  # noqa: E402
import requests  # noqa: E402

from review import diff as diff_module  # noqa: E402
from review.diff import GitHubError, PullRequestContext, github_get, valid_positions  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample_patch.txt"


def test_added_and_context_lines_are_valid_positions():
    patch = FIXTURE.read_text()
    assert valid_positions(patch) == {10, 11, 12, 13, 14, 15}


def test_removed_lines_are_never_valid_positions():
    patch = "@@ -1,3 +1,2 @@\n line_a\n-removed_line\n line_b\n"
    assert valid_positions(patch) == {1, 2}


def test_no_newline_marker_does_not_advance_position():
    patch = "@@ -1,1 +1,1 @@\n+only_line\n\\ No newline at end of file\n"
    assert valid_positions(patch) == {1}


def test_pull_request_context_reports_invalid_position_outside_diff():
    ctx = PullRequestContext(
        owner="o", repo="r", number=1, commit_id="sha", file_positions={"a.py": {10, 11}}
    )
    assert ctx.is_valid_position("a.py", 10) is True
    assert ctx.is_valid_position("a.py", 99) is False
    assert ctx.is_valid_position("b.py", 10) is False
    assert ctx.is_valid_position("a.py", None) is False


class _FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        # Real requests.Response.headers is case-insensitive, and _is_retryable relies
        # on that (checks lowercase "retry-after") - mirror it here so this fake can't
        # mask a real bug just because a test happened to match casing exactly.
        self.headers = requests.structures.CaseInsensitiveDict(headers or {})
        self.links: dict = {}
        self.text = "error body"

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(diff_module, "_sleep", lambda seconds: None)


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")


def test_transient_server_error_is_retried_then_succeeds(monkeypatch):
    responses = [_FakeResponse(503), _FakeResponse(200, payload={"ok": True})]

    def fake_get(url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(diff_module.requests, "get", fake_get)
    assert github_get("/repos/o/r") == {"ok": True}


def test_non_retryable_error_raises_immediately_without_retrying(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return _FakeResponse(404)

    monkeypatch.setattr(diff_module.requests, "get", fake_get)
    with pytest.raises(GitHubError):
        github_get("/repos/o/r")
    assert len(calls) == 1  # no retry for a real, non-transient error


def test_exhausting_all_retries_raises_github_error(monkeypatch):
    monkeypatch.setattr(diff_module.requests, "get", lambda url, **kwargs: _FakeResponse(503))
    with pytest.raises(GitHubError):
        github_get("/repos/o/r")


def test_secondary_rate_limit_with_retry_after_header_is_retried(monkeypatch):
    responses = [
        _FakeResponse(403, headers={"Retry-After": "0"}),
        _FakeResponse(200, payload={"ok": True}),
    ]

    def fake_get(url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(diff_module.requests, "get", fake_get)
    assert github_get("/repos/o/r") == {"ok": True}


def test_plain_403_without_retry_after_is_not_retried(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return _FakeResponse(403)  # a real permissions error, no Retry-After header

    monkeypatch.setattr(diff_module.requests, "get", fake_get)
    with pytest.raises(GitHubError):
        github_get("/repos/o/r")
    assert len(calls) == 1
