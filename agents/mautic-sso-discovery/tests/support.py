"""Test-only fake GitHub transport, following the same pattern as
agents/issue-reconciler/tests/support.py - kept as a separate, smaller copy
here since these two agent packages are independently installable and
don't share a test-only module.
"""
from __future__ import annotations

from typing import Any

from issue_reconciler.client import GitHubClient


class FakeResponse:
    def __init__(self, data: Any = None):
        self.status_code = 200
        self.ok = True
        self.reason = ""
        self.headers: dict = {}
        self._body = {"data": data}

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
