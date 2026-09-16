"""Everything this bot reads from GitHub: one fetch function per GraphQL
query, plus the two spokes (openspec/board-history) that turn raw fetches
into evidence. All read-only - see plan hard constraint #2, spokes return
evidence, never a decision.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from issue_reconciler.client import GitHubClient
from issue_reconciler.config import (
    MAX_TEXT_LENGTH,
    OPENSPEC_ARCHIVE_DIR,
    OPENSPEC_CHANGES_PATH,
    PROJECT_ID,
    REPO_NAME,
    REPO_OWNER,
    TRANSITION_LOOKBACK_DAYS,
)
from issue_reconciler.hashing import parse_fingerprint
from issue_reconciler.rules import AGENT_ACTOR
from issue_reconciler.types import LinkedPR

_BATCH_SIZE = 50


def _batches(items: list, size: int = _BATCH_SIZE):
    return (items[i : i + size] for i in range(0, len(items), size))


def _paginate(client: GitHubClient, query: str, variables: dict, get_page) -> list[dict]:
    """Shared cursor-pagination loop: get_page(response_data) returns the
    {pageInfo, nodes} dict to walk, or None to stop early.
    """
    nodes: list[dict] = []
    cursor = None
    while True:
        page = get_page(client.query(query, {**variables, "cursor": cursor}))
        if not page:
            break
        nodes.extend(page["nodes"])
        cursor = page["pageInfo"]["endCursor"] if page["pageInfo"]["hasNextPage"] else None
        if cursor is None:
            break
    return nodes


# ---- board items -----------------------------------------------------


class BoardItem(TypedDict):
    item_id: str
    issue_number: int
    status: str | None


_BOARD_QUERY = """
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
              ... on Issue { number repository { nameWithOwner } }
            }
          }
        }
      }
    }
  }
"""


def fetch_board_items(client: GitHubClient) -> list[BoardItem]:
    """Every board item, paginated, filtered to this repo's issues - the
    board is user-level and may hold items from other repos.
    """
    nodes = _paginate(client, _BOARD_QUERY, {"projectId": PROJECT_ID}, lambda data: (data.get("node") or {}).get("items"))
    items: list[BoardItem] = []
    expected_repo = f"{REPO_OWNER}/{REPO_NAME}"
    for node in nodes:
        content = node.get("content") or {}
        if content.get("__typename") != "Issue" or (content.get("repository") or {}).get("nameWithOwner") != expected_repo:
            continue
        status = node.get("status")
        items.append({"item_id": node["id"], "issue_number": content["number"], "status": status["name"] if status else None})
    return items


# ---- open issues -------------------------------------------------------


class OpenIssue(TypedDict):
    id: str  # GraphQL node ID - needed by writers.py for comment/close mutations
    number: int
    title: str
    labels: list[str]


_ISSUES_QUERY = """
  query OpenIssues($owner: String!, $name: String!, $cursor: String) {
    repository(owner: $owner, name: $name) {
      issues(first: 100, after: $cursor, states: [OPEN]) {
        pageInfo { hasNextPage endCursor }
        nodes { id number title labels(first: 20) { nodes { name } } }
      }
    }
  }
"""


def fetch_open_issues(client: GitHubClient) -> list[OpenIssue]:
    nodes = _paginate(client, _ISSUES_QUERY, {"owner": REPO_OWNER, "name": REPO_NAME}, lambda data: (data.get("repository") or {}).get("issues"))
    return [{"id": n["id"], "number": n["number"], "title": n["title"], "labels": [label["name"] for label in n["labels"]["nodes"]]} for n in nodes]


# ---- linked PRs (explicit references only) -----------------------------

_PR_FIELDS = "__typename ... on PullRequest { number title state merged mergedAt isDraft headRefName updatedAt reviewDecision }"


def _prs_query(issue_numbers: list[int]) -> str:
    aliases = "\n".join(
        f"""issue_{i}: issue(number: {n}) {{
      timelineItems(first: 50, itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT]) {{
        nodes {{
          __typename
          ... on CrossReferencedEvent {{ willCloseTarget source {{ {_PR_FIELDS} }} }}
          ... on ConnectedEvent {{ subject {{ {_PR_FIELDS} }} }}
        }}
      }}
    }}"""
        for i, n in enumerate(issue_numbers)
    )
    return f"query LinkedPRs($owner: String!, $name: String!) {{ repository(owner: $owner, name: $name) {{ {aliases} }} }}"


def _to_linked_pr(pr: dict) -> LinkedPR:
    return {
        "number": pr["number"], "title": pr.get("title", ""), "state": pr.get("state", "OPEN"),
        "merged": pr.get("merged", False), "merged_at": pr.get("mergedAt"), "is_draft": pr.get("isDraft", False),
        "head_ref_name": pr.get("headRefName", ""), "updated_at": pr.get("updatedAt"),
        "review_decision": pr.get("reviewDecision"),
    }


def fetch_linked_prs(client: GitHubClient, issue_numbers: list[int]) -> dict[int, list[LinkedPR]]:
    """Every PR that references an issue - by closing keyword, manual link,
    or a plain "#N" mention - batched into one query per _BATCH_SIZE issues,
    not one query per issue. The team's convention requires every PR
    description to name its issue, so any reference is trusted evidence;
    no model call needed to guess at an unlinked PR.
    """
    result: dict[int, list[LinkedPR]] = {}
    for batch in _batches(issue_numbers):
        repository = client.query(_prs_query(batch), {"owner": REPO_OWNER, "name": REPO_NAME}).get("repository") or {}
        for i, issue_number in enumerate(batch):
            node = repository.get(f"issue_{i}") or {}
            prs: list[LinkedPR] = []
            seen: set[int] = set()
            for item in node.get("timelineItems", {}).get("nodes", []):
                raw = None
                if item.get("__typename") == "CrossReferencedEvent":
                    source = item.get("source") or {}
                    if source.get("__typename") == "PullRequest":
                        raw = source
                elif item.get("__typename") == "ConnectedEvent" and (item.get("subject") or {}).get("__typename") == "PullRequest":
                    raw = item["subject"]
                if raw is None:
                    continue
                pr = _to_linked_pr(raw)
                if pr["number"] not in seen:
                    seen.add(pr["number"])
                    prs.append(pr)
            result[issue_number] = prs
    return result


# ---- OpenSpec proposals --------------------------------------------------

_ISSUE_REF_RE = re.compile(r"#(\d+)")
_TREE_QUERY = """
  query OpenSpecChangesTree($owner: String!, $name: String!, $expression: String!) {
    repository(owner: $owner, name: $name) { object(expression: $expression) { ... on Tree { entries { name type } } } }
  }
"""


def _proposals_query(names: list[str]) -> str:
    aliases = "\n".join(f'proposal_{i}: object(expression: "HEAD:{OPENSPEC_CHANGES_PATH}/{name}/proposal.md") {{ ... on Blob {{ text }} }}' for i, name in enumerate(names))
    return f"query OpenSpecProposals($owner: String!, $name: String!) {{ repository(owner: $owner, name: $name) {{ {aliases} }} }}"


def gather_openspec_proposals(client: GitHubClient) -> dict[int, list[str]]:
    """Maps issue number -> in-flight OpenSpec change names referencing it
    (e.g. "Closes #12"). One repo-wide fetch, not one per issue.
    """
    tree = client.query(_TREE_QUERY, {"owner": REPO_OWNER, "name": REPO_NAME, "expression": f"HEAD:{OPENSPEC_CHANGES_PATH}"})
    dirs = [e["name"] for e in ((tree.get("repository") or {}).get("object") or {}).get("entries", []) if e["type"] == "tree" and e["name"] != OPENSPEC_ARCHIVE_DIR]
    if not dirs:
        return {}

    repository = client.query(_proposals_query(dirs), {"owner": REPO_OWNER, "name": REPO_NAME}).get("repository") or {}
    by_issue: dict[int, list[str]] = {}
    for i, name in enumerate(dirs):
        text = ((repository.get(f"proposal_{i}") or {}).get("text") or "")[:MAX_TEXT_LENGTH]
        for issue_number in {int(n) for n in _ISSUE_REF_RE.findall(text)}:
            by_issue.setdefault(issue_number, []).append(name)
    return by_issue


# ---- board history (status-change actor/timestamp) -----------------------


class BoardHistoryEntry(TypedDict):
    last_status_actor: str | None
    last_status_at: str | None
    transition_count: int


_TRANSITION_DECISIONS = {"set_done", "set_in_progress"}
_COMMENTS_PER_ISSUE = 20


def _comments_query(issue_numbers: list[int]) -> str:
    aliases = "\n".join(f'issue_{i}: issue(number: {n}) {{ comments(last: {_COMMENTS_PER_ISSUE}) {{ nodes {{ author {{ login }} body createdAt }} }} }}' for i, n in enumerate(issue_numbers))
    return f"query IssueComments($owner: String!, $name: String!) {{ repository(owner: $owner, name: $name) {{ {aliases} }} }}"


def summarize_history(comments: list[dict], now: datetime) -> BoardHistoryEntry:
    """The GitHub API exposes no history of Projects v2 field-value changes,
    so this reconstructs "who last touched status, and when" from the
    agent's own fingerprinted comments (hashing.py) plus ordinary human
    comments as a proxy for recent human attention. The PAT backing the
    agent's writes belongs to a human account, so author login alone can't
    tell the two apart - the fingerprint is what does.
    """
    lookback = timedelta(days=TRANSITION_LOOKBACK_DAYS)
    transition_count = sum(
        1
        for c in comments
        if (fp := parse_fingerprint(c["body"])) and fp["decision"] in _TRANSITION_DECISIONS and now - datetime.fromisoformat(c["created_at"]) < lookback
    )
    if not comments:
        return {"last_status_actor": None, "last_status_at": None, "transition_count": transition_count}

    last = comments[-1]
    actor = AGENT_ACTOR if parse_fingerprint(last["body"]) else last["author"]
    return {"last_status_actor": actor, "last_status_at": last["created_at"], "transition_count": transition_count}


def gather_board_history(client: GitHubClient, issue_numbers: list[int], now: datetime | None = None) -> dict[int, BoardHistoryEntry]:
    now = now or datetime.now(timezone.utc)
    comments_by_issue: dict[int, list[dict]] = {}
    for batch in _batches(issue_numbers):
        repository = client.query(_comments_query(batch), {"owner": REPO_OWNER, "name": REPO_NAME}).get("repository") or {}
        for i, issue_number in enumerate(batch):
            nodes = (repository.get(f"issue_{i}") or {}).get("comments", {}).get("nodes", [])
            comments_by_issue[issue_number] = [{"author": (c.get("author") or {}).get("login"), "body": c["body"], "created_at": c["createdAt"]} for c in nodes]
    return {n: summarize_history(comments_by_issue.get(n, []), now) for n in issue_numbers}
