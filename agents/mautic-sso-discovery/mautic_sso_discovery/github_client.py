"""Thin GraphQL client: auth header, retry with jittered backoff on transient
failures (5xx, network errors, secondary rate limit), and no retry on client
errors (4xx other than 403/429 rate-limit) or GraphQL-level errors, since
those won't succeed by resending the same query.

Self-contained on purpose: this package doesn't depend on
agents/issue-reconciler/, even though that package has an equivalent
client, so mautic-sso-discovery has no cross-package dependency to install
or version.
"""
from __future__ import annotations

import random
import time
from typing import Any, Callable

import requests

_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"

_MAX_ATTEMPTS = 4
_BASE_BACKOFF_SECONDS = 0.5


class GraphQLError(RuntimeError):
    def __init__(self, message: str, errors: Any):
        super().__init__(message)
        self.errors = errors


class FatalHTTPError(RuntimeError):
    """A non-2xx response that isn't rate-limiting or a server error -
    retrying the same query won't change the outcome. Kept as its own type
    so the retry loop's broad except clause below doesn't swallow it.
    """


# A transport just needs .status_code, .ok, .reason, .headers, and .json() -
# whatever requests.Response or a test's fake response provides. Not worth a
# Protocol class for a shape nothing ever type-checks against at runtime.
Transport = Callable[[str, dict, dict], Any]


def _default_transport(url: str, body: dict, headers: dict) -> Any:
    return requests.post(url, json=body, headers=headers, timeout=30)


def _is_retryable_graphql_error(errors: Any) -> bool:
    if not isinstance(errors, list):
        return False
    return any(isinstance(e, dict) and e.get("type") == "RATE_LIMITED" for e in errors)


def _is_rate_limit_403(response: Any) -> bool:
    """A 403 is only ever rate-limiting if the response carries actual
    rate-limit evidence (a retry-after header, or GitHub's exhausted-quota
    header). A plain 403 with neither is a permission problem (e.g. a
    misscoped token) - retrying that just burns four attempts and reports a
    misleading "rate limited" error instead of the real cause.
    """
    if response.headers.get("retry-after"):
        return True
    return response.headers.get("x-ratelimit-remaining") == "0"


class GitHubClient:
    def __init__(
        self,
        token: str,
        *,
        transport: Transport | None = None,
        max_attempts: int = _MAX_ATTEMPTS,
        base_backoff: float = _BASE_BACKOFF_SECONDS,
        sleep: Callable[[float], None] | None = None,
    ):
        self._token = token
        self._transport = transport or _default_transport
        self._max_attempts = max_attempts
        self._base_backoff = base_backoff
        self._sleep = sleep or time.sleep

    def query(self, query: str, variables: dict | None = None) -> Any:
        last_error: Exception = RuntimeError("unreachable")

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._transport(
                    _GRAPHQL_ENDPOINT,
                    {"query": query, "variables": variables or {}},
                    {
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json",
                        "Accept": "application/vnd.github+json",
                    },
                )

                if response.status_code == 429 or (response.status_code == 403 and _is_rate_limit_403(response)):
                    retry_after = response.headers.get("retry-after")
                    last_error = RuntimeError(f"rate limited (status {response.status_code})")
                    if attempt < self._max_attempts:
                        self._backoff(attempt, floor=float(retry_after) if retry_after else None)
                    continue

                if response.status_code == 403:
                    raise FatalHTTPError(f"GitHub API request forbidden (status 403): {response.reason}")

                if response.status_code >= 500:
                    last_error = RuntimeError(f"transient server error (status {response.status_code})")
                    if attempt < self._max_attempts:
                        self._backoff(attempt)
                    continue

                if not response.ok:
                    raise FatalHTTPError(f"GitHub API request failed: {response.status_code} {response.reason}")

                body = response.json()
                if body.get("errors"):
                    if _is_retryable_graphql_error(body["errors"]):
                        last_error = GraphQLError("retryable GraphQL error", body["errors"])
                        if attempt < self._max_attempts:
                            self._backoff(attempt)
                        continue
                    raise GraphQLError("GraphQL request returned errors", body["errors"])

                return body.get("data")
            except (GraphQLError, FatalHTTPError):
                raise
            except Exception as error:
                last_error = error
                if attempt < self._max_attempts:
                    self._backoff(attempt)

        raise last_error

    def _backoff(self, attempt: int, floor: float | None = None) -> None:
        exponential = self._base_backoff * (2 ** (attempt - 1))
        jitter = random.random() * self._base_backoff  # noqa: S311 - backoff timing, not a security context
        delay = max(floor or 0, exponential + jitter)
        self._sleep(delay)
