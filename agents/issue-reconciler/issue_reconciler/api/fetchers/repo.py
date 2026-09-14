from __future__ import annotations

from typing import TypedDict

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.config import (
    MAX_TEXT_LENGTH,
    OPENSPEC_ARCHIVE_DIR,
    OPENSPEC_CHANGES_PATH,
    REPO_NAME,
    REPO_OWNER,
)

_TREE_QUERY = """
  query OpenSpecChangesTree($owner: String!, $name: String!, $expression: String!) {
    repository(owner: $owner, name: $name) {
      object(expression: $expression) {
        ... on Tree {
          entries { name type }
        }
      }
    }
  }
"""


class OpenSpecChange(TypedDict):
    name: str
    proposal_text: str


def _build_proposals_query(names: list[str]) -> str:
    aliases = "\n".join(
        f"""
    proposal_{i}: object(expression: "HEAD:{OPENSPEC_CHANGES_PATH}/{name}/proposal.md") {{
      ... on Blob {{ text }}
    }}"""
        for i, name in enumerate(names)
    )
    return f"""query OpenSpecProposals($owner: String!, $name: String!) {{
    repository(owner: $owner, name: $name) {{ {aliases} }}
  }}"""


def fetch_openspec_changes(client: GitHubClient) -> list[OpenSpecChange]:
    """Lists in-flight OpenSpec changes (excluding the archive) with their
    proposal text, truncated. Correlating a proposal to a specific issue
    number happens in the openspec_evidence spoke, not here - this fetcher
    only normalizes what the repo contains.
    """
    tree_data = client.query(
        _TREE_QUERY, {"owner": REPO_OWNER, "name": REPO_NAME, "expression": f"HEAD:{OPENSPEC_CHANGES_PATH}"}
    )
    obj = (tree_data.get("repository") or {}).get("object")
    dirs = [e for e in (obj or {}).get("entries", []) if e["type"] == "tree" and e["name"] != OPENSPEC_ARCHIVE_DIR]

    if not dirs:
        return []

    query = _build_proposals_query([d["name"] for d in dirs])
    proposals_data = client.query(query, {"owner": REPO_OWNER, "name": REPO_NAME})
    repository = proposals_data.get("repository") or {}

    return [
        {
            "name": d["name"],
            "proposal_text": ((repository.get(f"proposal_{i}") or {}).get("text") or "")[:MAX_TEXT_LENGTH],
        }
        for i, d in enumerate(dirs)
    ]
