from __future__ import annotations

from typing import TypedDict

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.config import REPO_NAME, REPO_OWNER

_QUERY = """
  query OpenIssues($owner: String!, $name: String!, $cursor: String) {
    repository(owner: $owner, name: $name) {
      issues(first: 100, after: $cursor, states: [OPEN]) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          number
          title
          labels(first: 20) { nodes { name } }
        }
      }
    }
  }
"""


class OpenIssue(TypedDict):
    id: str  # GraphQL node ID - required by the writer for comment/close mutations
    number: int
    title: str
    labels: list[str]


def fetch_open_issues(client: GitHubClient) -> list[OpenIssue]:
    issues: list[OpenIssue] = []
    cursor = None

    while True:
        data = client.query(_QUERY, {"owner": REPO_OWNER, "name": REPO_NAME, "cursor": cursor})
        page = (data.get("repository") or {}).get("issues")
        if not page:
            break

        for node in page["nodes"]:
            issues.append(
                {
                    "id": node["id"],
                    "number": node["number"],
                    "title": node["title"],
                    "labels": [label["name"] for label in node["labels"]["nodes"]],
                }
            )

        if page["pageInfo"]["hasNextPage"]:
            cursor = page["pageInfo"]["endCursor"]
        else:
            break

    return issues
