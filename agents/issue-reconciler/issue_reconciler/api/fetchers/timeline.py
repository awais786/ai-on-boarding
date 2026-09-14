from __future__ import annotations

from typing import TypedDict

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.config import REPO_NAME, REPO_OWNER

_BATCH_SIZE = 50
_COMMENTS_PER_ISSUE = 20


class IssueComment(TypedDict):
    author: str | None
    body: str
    created_at: str


def _build_query(issue_numbers: list[int]) -> str:
    aliases = "\n".join(
        f"""
    issue_{i}: issue(number: {n}) {{
      comments(last: {_COMMENTS_PER_ISSUE}) {{
        nodes {{
          author {{ login }}
          body
          createdAt
        }}
      }}
    }}"""
        for i, n in enumerate(issue_numbers)
    )
    return f"""query IssueComments($owner: String!, $name: String!) {{
    repository(owner: $owner, name: $name) {{ {aliases} }}
  }}"""


def fetch_issue_comments(client: GitHubClient, issue_numbers: list[int]) -> dict[int, list[IssueComment]]:
    """Fetches each issue's most recent comments, batched in one request.
    This is how board_history recovers status-change actor/timestamp: the
    agent's own writes carry a fingerprint (see fingerprint.py), and this is
    the only audit trail available since Projects v2 field changes aren't
    exposed on the issue timeline.
    """
    result: dict[int, list[IssueComment]] = {}

    for start in range(0, len(issue_numbers), _BATCH_SIZE):
        batch = issue_numbers[start : start + _BATCH_SIZE]
        data = client.query(_build_query(batch), {"owner": REPO_OWNER, "name": REPO_NAME})
        repository = data.get("repository") or {}

        for i, issue_number in enumerate(batch):
            node = repository.get(f"issue_{i}") or {}
            comments = node.get("comments", {}).get("nodes", [])
            result[issue_number] = [
                {
                    "author": (c.get("author") or {}).get("login"),
                    "body": c["body"],
                    "created_at": c["createdAt"],
                }
                for c in comments
            ]

    return result
