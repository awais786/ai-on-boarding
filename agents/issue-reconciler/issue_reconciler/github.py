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
    FUZZY_CANDIDATE_LIMIT,
    FUZZY_CANDIDATE_LOOKBACK_DAYS,
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
              ... on Issue { number repository { name } }
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
    items: list[BoardItem] = []
    cursor = None
    while True:
        data = client.query(_BOARD_QUERY, {"projectId": PROJECT_ID, "cursor": cursor})
        page = (data.get("node") or {}).get("items")
        if not page:
            break
        for node in page["nodes"]:
            content = node.get("content") or {}
            if content.get("__typename") != "Issue" or (content.get("repository") or {}).get("name") != REPO_NAME:
                continue
            status = node.get("status")
            items.append({"item_id": node["id"], "issue_number": content["number"], "status": status["name"] if status else None})
        cursor = page["pageInfo"]["endCursor"] if page["pageInfo"]["hasNextPage"] else None
        if cursor is None:
            break
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
    issues: list[OpenIssue] = []
    cursor = None
    while True:
        data = client.query(_ISSUES_QUERY, {"owner": REPO_OWNER, "name": REPO_NAME, "cursor": cursor})
        page = (data.get("repository") or {}).get("issues")
        if not page:
            break
        for node in page["nodes"]:
            issues.append({"id": node["id"], "number": node["number"], "title": node["title"], "labels": [label["name"] for label in node["labels"]["nodes"]]})
        cursor = page["pageInfo"]["endCursor"] if page["pageInfo"]["hasNextPage"] else None
        if cursor is None:
            break
    return issues


# ---- linked PRs (explicit references only) -----------------------------

_PR_FIELDS = "__typename ... on PullRequest { number title state merged mergedAt isDraft headRefName }"


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
        "head_ref_name": pr.get("headRefName", ""), "match_source": "explicit", "confidence": 1.0,
    }


def fetch_linked_prs(client: GitHubClient, issue_numbers: list[int]) -> dict[int, list[LinkedPR]]:
    """Explicit PR references (closing keywords, manually linked), batched
    into one query per _BATCH_SIZE issues - not one query per issue. Fuzzy
    matching for issues with no explicit reference is fuzzy.py's job, over
    PRs this function does not return.
    """
    result: dict[int, list[LinkedPR]] = {}
    for start in range(0, len(issue_numbers), _BATCH_SIZE):
        batch = issue_numbers[start : start + _BATCH_SIZE]
        repository = client.query(_prs_query(batch), {"owner": REPO_OWNER, "name": REPO_NAME}).get("repository") or {}
        for i, issue_number in enumerate(batch):
            node = repository.get(f"issue_{i}") or {}
            prs: list[LinkedPR] = []
            seen: set[int] = set()
            for item in node.get("timelineItems", {}).get("nodes", []):
                raw = None
                if item.get("__typename") == "CrossReferencedEvent":
                    source = item.get("source") or {}
                    if item.get("willCloseTarget") and source.get("__typename") == "PullRequest":
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


# ---- candidate PRs for fuzzy matching -----------------------------------


class CandidatePR(TypedDict):
    number: int
    title: str
    head_ref_name: str
    state: str  # "OPEN" | "MERGED"
    merged: bool
    merged_at: str | None
    is_draft: bool


_CANDIDATE_FIELDS = "number title headRefName state isDraft mergedAt"
_CANDIDATE_QUERY = f"""
  query CandidatePRs($owner: String!, $name: String!, $limit: Int!) {{
    repository(owner: $owner, name: $name) {{
      open: pullRequests(states: [OPEN], first: $limit, orderBy: {{ field: UPDATED_AT, direction: DESC }}) {{ nodes {{ {_CANDIDATE_FIELDS} }} }}
      merged: pullRequests(states: [MERGED], first: $limit, orderBy: {{ field: UPDATED_AT, direction: DESC }}) {{ nodes {{ {_CANDIDATE_FIELDS} }} }}
    }}
  }}
"""


def fetch_candidate_prs(client: GitHubClient, now: datetime | None = None) -> list[CandidatePR]:
    """Bounded, repo-wide pool of open PRs + PRs merged in the last
    FUZZY_CANDIDATE_LOOKBACK_DAYS days - the search space fuzzy.py compares
    each unmatched issue against. One query per run, not per issue.
    """
    now = now or datetime.now(timezone.utc)
    repository = client.query(_CANDIDATE_QUERY, {"owner": REPO_OWNER, "name": REPO_NAME, "limit": FUZZY_CANDIDATE_LIMIT}).get("repository")
    if not repository:
        return []
    cutoff = now - timedelta(days=FUZZY_CANDIDATE_LOOKBACK_DAYS)
    recent_merges = [pr for pr in repository["merged"]["nodes"] if pr.get("mergedAt") and datetime.fromisoformat(pr["mergedAt"]) >= cutoff]

    seen: set[int] = set()
    candidates: list[CandidatePR] = []
    for pr in [*repository["open"]["nodes"], *recent_merges]:
        if pr["number"] in seen:
            continue
        seen.add(pr["number"])
        candidates.append({"number": pr["number"], "title": pr["title"], "head_ref_name": pr["headRefName"], "state": pr["state"], "merged": pr["state"] == "MERGED", "merged_at": pr.get("mergedAt"), "is_draft": pr["isDraft"]})
    return candidates


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
    for start in range(0, len(issue_numbers), _BATCH_SIZE):
        batch = issue_numbers[start : start + _BATCH_SIZE]
        repository = client.query(_comments_query(batch), {"owner": REPO_OWNER, "name": REPO_NAME}).get("repository") or {}
        for i, issue_number in enumerate(batch):
            nodes = (repository.get(f"issue_{i}") or {}).get("comments", {}).get("nodes", [])
            comments_by_issue[issue_number] = [{"author": (c.get("author") or {}).get("login"), "body": c["body"], "created_at": c["createdAt"]} for c in nodes]
    return {n: summarize_history(comments_by_issue.get(n, []), now) for n in issue_numbers}
