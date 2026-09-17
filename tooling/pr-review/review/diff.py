"""Talks to the GitHub API for the publishing pipeline: fetches a pull request's diff
and resolves which (file, line) positions are valid targets for an inline review
comment. `github_get`/`github_post` are also the HTTP helpers `publish.py` uses to
fetch existing comments and post new ones, so there is one place that knows how to
authenticate to GitHub, not several.

See openspec/changes/add-pr-review-agent/design.md - Decision 6, and the spec's
"Fall back to a general comment for unattachable findings" requirement.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_ROOT = "https://api.github.com"

# GET is idempotent, so a transient failure (a 5xx, or either of GitHub's rate limits)
# can be safely retried; POST is not, so it is deliberately excluded (urllib3's own
# default `allowed_methods` already excludes it) - retrying a POST that actually
# succeeded server-side before a delayed/dropped response would create a duplicate PR
# comment, which nothing downstream would catch (publish.py's dedupe only looks across
# separate runs, not within one run's own retry). 403 is included alongside 429/5xx
# because GitHub's secondary rate limit uses 403 with a Retry-After header, which
# `respect_retry_after_header` (on by default) honours; a persistent, non-rate-limit
# 403 just retries a few times against unchanging input before failing the same way it
# always would have, at the cost of a bounded few seconds. Connection-level failures
# (a dropped connection, a timeout before any response exists) are retried too - this
# is real urllib3 behaviour, not just status-code matching, unlike the hand-rolled
# version this replaced, which only ever inspected `response.status_code` and so
# never engaged for a failure that occurred before a response existed at all.
_RETRY = Retry(
    total=4,
    backoff_factor=1.0,
    status_forcelist=[403, 429, 502, 503, 504],
    respect_retry_after_header=True,
    retry_after_max=60,  # this pipeline runs in CI; do not sleep through an entire job budget
)

_session = requests.Session()
# Mounted for both schemes - the real API is always https, but mounting http:// too
# costs nothing in production and lets tests exercise the real retry policy against
# a local HTTP server rather than mocking around it.
_adapter = HTTPAdapter(max_retries=_RETRY)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


class GitHubError(RuntimeError):
    """A GitHub API call did not succeed."""


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise GitHubError("GITHUB_TOKEN is not set - required to call the GitHub API.")
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request(method: str, path: str, url: str, **kwargs) -> requests.Response:
    """A single HTTP call through `_session`, so it picks up `_RETRY`. Retries that
    exhaust, and connection-level failures, surface from `_session` as a
    `requests.RequestException` (not a response object) - caught here and converted
    to the one error type this module raises, so callers only ever handle
    `GitHubError`, regardless of whether the failure was transient-then-exhausted or
    immediate.
    """
    try:
        response = _session.request(method, url, headers=_headers(), timeout=30, **kwargs)
    except requests.RequestException as exc:
        raise GitHubError(f"{path} failed: {exc}") from exc
    if response.status_code >= 400:
        raise GitHubError(f"{path} failed: {response.status_code} {response.text}")
    return response


def github_get(path: str, params: dict | None = None) -> list | dict:
    """GET against the GitHub API, following pagination for list responses."""
    url = f"{API_ROOT}{path}"
    results: list = []
    while url:
        response = _request("GET", path, url, params=params)
        payload = response.json()
        if not isinstance(payload, list):
            return payload
        results.extend(payload)
        url = response.links.get("next", {}).get("url")
        params = None  # the next URL already carries the query string
    return results


def github_post(path: str, json: dict) -> dict:
    url = f"{API_ROOT}{path}"
    response = _request("POST", path, url, json=json)
    return response.json()


_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def valid_positions(patch: str) -> set[int]:
    """The new-file line numbers a patch's hunks make available for an inline comment.

    Mirrors what GitHub's review-comment API accepts as a position: any line the diff
    shows on the right-hand (new) side - added or unchanged context - but not a line
    that only existed on the old side, and not a "no newline at end of file" marker.
    """
    positions: set[int] = set()
    new_line = 0
    for raw_line in patch.splitlines():
        header = _HUNK_HEADER.match(raw_line)
        if header:
            new_line = int(header.group(1))
            continue
        if new_line == 0:
            continue
        if raw_line.startswith("-") or raw_line.startswith("\\"):
            continue
        positions.add(new_line)
        new_line += 1
    return positions


@dataclass
class PullRequestContext:
    owner: str
    repo: str
    number: int
    commit_id: str
    file_positions: dict[str, set[int]] = field(default_factory=dict)

    def is_valid_position(self, path: str, line: int | None) -> bool:
        if line is None:
            return False
        return line in self.file_positions.get(path, set())


def fetch_pull_request_context(owner: str, repo: str, number: int) -> PullRequestContext:
    pr = github_get(f"/repos/{owner}/{repo}/pulls/{number}")
    files = github_get(f"/repos/{owner}/{repo}/pulls/{number}/files", params={"per_page": 100})
    file_positions = {
        entry["filename"]: valid_positions(entry["patch"])
        for entry in files
        if entry.get("patch")
    }
    return PullRequestContext(
        owner=owner,
        repo=repo,
        number=number,
        commit_id=pr["head"]["sha"],
        file_positions=file_positions,
    )
