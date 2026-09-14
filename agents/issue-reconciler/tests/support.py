"""Test-only helpers: fake GitHub/Anthropic transports so github.py, fuzzy.py,
and orchestrator.py can be unit tested without live credentials.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from issue_reconciler.client import GitHubClient


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
    """Returns canned data payloads in call order. Use only when a function
    issues queries in a known, fixed sequence (a single fetcher).
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


def make_routed_client(routes: list[tuple[str, Any]]) -> tuple[GitHubClient, list[dict]]:
    """Routes by a substring of the query text (each query in this codebase
    has a distinct operation name) instead of call order, since code that
    fans out several queries concurrently has no fixed call order a test
    should have to predict (the orchestrator).
    """
    calls: list[dict] = []

    def transport(_url: str, body: dict, _headers: dict):
        calls.append(body)
        for match, response in routes:
            if match in body["query"]:
                data = response(body["variables"]) if callable(response) else response
                return FakeResponse(data=data)
        raise AssertionError(f"no route matched query:\n{body['query']}")

    client = GitHubClient("test-token", transport=transport, sleep=lambda _: None)
    return client, calls


class FakeAnthropicMessages:
    """Stands in for client.messages on a real Anthropic client. handler
    receives the full request kwargs and returns either a dict (the parsed
    JSON the model "replied" with) or raises to simulate an API error.
    """

    def __init__(self, handler: Callable[[dict], dict]):
        self._handler = handler
        self.call_count = 0

    def create(self, **kwargs):
        self.call_count += 1
        result = self._handler(kwargs)
        text = json.dumps(result)
        return _FakeMessage(text)


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeTextBlock(text)]


class _FakeTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class FakeAnthropicClient:
    def __init__(self, handler: Callable[[dict], dict]):
        self.messages = FakeAnthropicMessages(handler)
