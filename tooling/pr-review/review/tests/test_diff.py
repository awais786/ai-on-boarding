"""Tests for review.diff, written from the pr-review spec.

- "Post each finding as its own isolated comment" (the inline case) and "Fall back to
  a general comment for unattachable findings" both depend on correctly telling which
  (file, line) positions a pull request's diff actually makes available.
"""
from __future__ import annotations

import json as json_module
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

import pytest  # noqa: E402

from review import diff as diff_module  # noqa: E402
from review.diff import GitHubError, PullRequestContext, github_get, github_post, valid_positions  # noqa: E402

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


class _ScriptedServer:
    """A real local HTTP server that plays back a scripted sequence of responses, one
    per request received, repeating the last entry once exhausted. Exercises the
    actual `_session` (a real `HTTPAdapter` with a real `urllib3.util.retry.Retry`)
    end to end - mocking `requests.get`/`.post` directly would no longer prove
    anything, since the retry loop now lives inside urllib3's own connection
    handling, not in code this module calls directly.
    """

    def __init__(self, script: list[tuple[int, dict, bytes]]):
        self.script = script
        self.requests: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self):
                outer.requests.append(self.command)
                index = min(len(outer.requests) - 1, len(outer.script) - 1)
                status, headers, body = outer.script[index]
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._serve()

            def do_POST(self):
                self._serve()

            def log_message(self, *args):
                pass  # keep test output quiet

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._server.shutdown()
        self._thread.join()


def _response(status: int, payload=None, headers: dict | None = None) -> tuple[int, dict, bytes]:
    return status, headers or {}, json_module.dumps(payload if payload is not None else []).encode()


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")


@pytest.fixture(autouse=True)
def _real_api_root_restored(monkeypatch):
    # Each test below points diff_module.API_ROOT at a local server; restore the
    # real value afterwards regardless of how the test exits.
    original = diff_module.API_ROOT
    yield
    diff_module.API_ROOT = original


def test_transient_server_error_is_retried_then_succeeds():
    with _ScriptedServer(
        [_response(503, headers={"Retry-After": "1"}), _response(200, payload={"ok": True})]
    ) as server:
        diff_module.API_ROOT = server.url
        assert github_get("/repos/o/r") == {"ok": True}
        assert len(server.requests) == 2


def test_non_retryable_error_raises_immediately_without_retrying():
    with _ScriptedServer([_response(404)]) as server:
        diff_module.API_ROOT = server.url
        with pytest.raises(GitHubError):
            github_get("/repos/o/r")
        assert len(server.requests) == 1  # no retry for a real, non-transient error


def test_exhausting_all_retries_raises_github_error():
    with _ScriptedServer([_response(503, headers={"Retry-After": "1"})]) as server:
        diff_module.API_ROOT = server.url
        with pytest.raises(GitHubError):
            github_get("/repos/o/r")
        assert len(server.requests) == diff_module._RETRY.total + 1


def test_secondary_rate_limit_with_retry_after_header_is_retried():
    with _ScriptedServer(
        [_response(403, headers={"Retry-After": "1"}), _response(200, payload={"ok": True})]
    ) as server:
        diff_module.API_ROOT = server.url
        assert github_get("/repos/o/r") == {"ok": True}


def test_post_is_never_retried_even_on_a_transient_status():
    """The correctness case this retry design exists to protect: a POST (creating a
    PR comment/review) must never be retried on a transient status, because a
    delayed/dropped success response would otherwise cause a silent duplicate
    comment that nothing downstream de-duplicates within a single run.
    """
    with _ScriptedServer(
        [_response(503, headers={"Retry-After": "1"}), _response(200, payload={"ok": True})]
    ) as server:
        diff_module.API_ROOT = server.url
        with pytest.raises(GitHubError):
            github_post("/repos/o/r/issues/1/comments", {"body": "hi"})
        assert len(server.requests) == 1  # never retried, regardless of status


def test_connection_failure_before_any_response_is_still_a_github_error(monkeypatch):
    """A failure with no HTTP response at all (connection refused - nothing is
    listening on this port) must still surface as GitHubError, not an unhandled
    requests exception - this was the previous status-code-only retry's real gap.
    This test only checks exception translation, not retry count, so retries are
    dropped to 0 here - a real connection refusal has no Retry-After to exploit for
    speed the way the status-based tests above do, and would otherwise pay the full
    ~15s of real exponential backoff for no added coverage.
    """
    monkeypatch.setattr(diff_module._RETRY, "total", 0)
    diff_module.API_ROOT = "http://127.0.0.1:1"  # nothing listens here
    with pytest.raises(GitHubError):
        github_get("/repos/o/r")


def test_retry_policy_excludes_post_and_covers_transient_statuses():
    """Locks in the retry policy's shape directly, independent of live server
    timing, so a future edit that accidentally re-adds POST or drops a status code
    is caught even if the end-to-end tests above are ever skipped or slow."""
    retry = diff_module._RETRY
    assert "POST" not in retry.allowed_methods
    assert "GET" in retry.allowed_methods
    assert set(retry.status_forcelist) >= {403, 429, 502, 503, 504}
