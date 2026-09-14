from __future__ import annotations

from typing import TypedDict

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.config import PROJECT_ID, REPO_NAME

_QUERY = """
  query BoardItems($projectId: ID!, $cursor: String) {
    node(id: $projectId) {
      ... on ProjectV2 {
        items(first: 100, after: $cursor) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            status: fieldValueByName(name: "Status") {
              ... on ProjectV2ItemFieldSingleSelectValue { name }
            }
            content {
              __typename
              ... on Issue {
                number
                repository { name }
              }
            }
          }
        }
      }
    }
  }
"""


class BoardItem(TypedDict):
    item_id: str
    issue_number: int
    status: str | None


def fetch_board_items(client: GitHubClient) -> list[BoardItem]:
    """Fetches every board item, paginated, filtered to this repo's issues.
    The board is user-level and may hold items from other repos - never
    touch those (see plan "Board scope warning").
    """
    items: list[BoardItem] = []
    cursor = None

    while True:
        data = client.query(_QUERY, {"projectId": PROJECT_ID, "cursor": cursor})
        page = (data.get("node") or {}).get("items")
        if not page:
            break

        for node in page["nodes"]:
            content = node.get("content") or {}
            if content.get("__typename") != "Issue":
                continue
            repository = content.get("repository") or {}
            if repository.get("name") != REPO_NAME:
                continue

            status = node.get("status")
            items.append(
                {
                    "item_id": node["id"],
                    "issue_number": content["number"],
                    "status": status["name"] if status else None,
                }
            )

        if page["pageInfo"]["hasNextPage"]:
            cursor = page["pageInfo"]["endCursor"]
        else:
            break

    return items
