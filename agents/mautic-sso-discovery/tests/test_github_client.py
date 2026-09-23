from __future__ import annotations

import pytest
from support import FakeResponse

from mautic_sso_discovery.github_client import FatalHTTPError, GitHubClient, GraphQLError


def test_returns_data_on_a_successful_response():
    client = GitHubClient("t", sleep=lambda _: None, transport=lambda *_: FakeResponse(data={"hello": "world"}))
    assert client.query("query { hello }") == {"hello": "world"}


def test_retries_transient_5xx_and_eventually_succeeds():
    calls = {"n": 0}

    def transport(*_args):
        calls["n"] += 1
        if calls["n"] < 3:
            return FakeResponse(status_code=502, reason="Bad Gateway")
        return FakeResponse(data={"ok": True})

    client = GitHubClient("t", sleep=lambda _: None, transport=transport)
    assert client.query("query { ok }") == {"ok": True}
    assert calls["n"] == 3


def test_retries_rate_limited_response_honoring_retry_after():
    calls = {"n": 0}
    sleeps = []

    def transport(*_args):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(status_code=403, headers={"retry-after": "2"})
        return FakeResponse(data={"ok": True})

    client = GitHubClient("t", sleep=lambda s: sleeps.append(s), transport=transport)
    client.query("query { ok }")

    assert calls["n"] == 2
    assert sleeps[0] >= 2.0


def test_gives_up_after_max_attempts_and_surfaces_the_last_error():
    client = GitHubClient(
        "t", max_attempts=2, sleep=lambda _: None,
        transport=lambda *_: FakeResponse(status_code=500, reason="Internal Server Error"),
    )
    with pytest.raises(RuntimeError, match="transient server error"):
        client.query("query { ok }")


def test_does_not_retry_a_non_retryable_graphql_error():
    calls = {"n": 0}

    def transport(*_args):
        calls["n"] += 1
        return FakeResponse(errors=[{"type": "NOT_FOUND", "message": "no such field"}])

    client = GitHubClient("t", sleep=lambda _: None, transport=transport)
    with pytest.raises(GraphQLError):
        client.query("query { ok }")
    assert calls["n"] == 1


def test_retries_a_rate_limited_graphql_level_error():
    calls = {"n": 0}

    def transport(*_args):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(errors=[{"type": "RATE_LIMITED", "message": "slow down"}])
        return FakeResponse(data={"ok": True})

    client = GitHubClient("t", sleep=lambda _: None, transport=transport)
    assert client.query("query { ok }") == {"ok": True}
    assert calls["n"] == 2


def test_retries_a_403_with_exhausted_rate_limit_header_even_without_retry_after():
    calls = {"n": 0}

    def transport(*_args):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(status_code=403, headers={"x-ratelimit-remaining": "0"})
        return FakeResponse(data={"ok": True})

    client = GitHubClient("t", sleep=lambda _: None, transport=transport)
    assert client.query("query { ok }") == {"ok": True}
    assert calls["n"] == 2


def test_a_plain_403_with_no_rate_limit_evidence_fails_fast_as_forbidden():
    """A misconfigured/underscoped BOARD_TOKEN returns 403 with none of
    GitHub's rate-limit headers - that's a permission problem, not
    rate-limiting, and retrying it four times just delays a misleading
    error instead of failing fast with the real cause.
    """
    calls = {"n": 0}

    def transport(*_args):
        calls["n"] += 1
        return FakeResponse(status_code=403, reason="Forbidden")

    client = GitHubClient("t", sleep=lambda _: None, transport=transport)
    with pytest.raises(FatalHTTPError, match="403"):
        client.query("query { ok }")
    assert calls["n"] == 1


def test_does_not_retry_a_plain_4xx_client_error():
    calls = {"n": 0}

    def transport(*_args):
        calls["n"] += 1
        return FakeResponse(status_code=400, reason="Bad Request")

    client = GitHubClient("t", sleep=lambda _: None, transport=transport)
    with pytest.raises(RuntimeError, match="400"):
        client.query("query { ok }")
    assert calls["n"] == 1
