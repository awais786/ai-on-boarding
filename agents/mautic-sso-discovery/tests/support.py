"""Test-only fake GitHub transport for this package's own GitHubClient."""
from __future__ import annotations

from typing import Any

from mautic_sso_discovery.github_client import GitHubClient


class FakeResponse:
    def __init__(self, status_code: int = 200, data: Any = None, errors: Any = None, headers: dict | None = None, reason: str = ""):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.reason = reason
        self.headers = headers or {}
        self._body = {}
        if data is not None:
            self._body["data"] = data
        if errors is not None:
            self._body["errors"] = errors

    def json(self) -> dict:
        return self._body


def make_sequential_client(responses: list[Any]) -> tuple[GitHubClient, list[dict]]:
    """Returns canned data payloads in call order - use only when the code
    under test issues queries in a known, fixed sequence.
    """
    calls: list[dict] = []
    index = {"i": 0}

    def transport(_url: str, body: dict, _headers: dict):
        calls.append(body)
        data = responses[index["i"]]
        index["i"] += 1
        return FakeResponse(data=data)

    client = GitHubClient("test-token", transport=transport, sleep=lambda _: None)
    return client, calls
