from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TypedDict

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.config import (
    FUZZY_CANDIDATE_LIMIT,
    FUZZY_CANDIDATE_LOOKBACK_DAYS,
    REPO_NAME,
    REPO_OWNER,
)

_PR_FIELDS = "number title headRefName state isDraft mergedAt"

_QUERY = f"""
  query CandidatePRs($owner: String!, $name: String!, $limit: Int!) {{
    repository(owner: $owner, name: $name) {{
      open: pullRequests(states: [OPEN], first: $limit, orderBy: {{ field: UPDATED_AT, direction: DESC }}) {{
        nodes {{ {_PR_FIELDS} }}
      }}
      merged: pullRequests(states: [MERGED], first: $limit, orderBy: {{ field: UPDATED_AT, direction: DESC }}) {{
        nodes {{ {_PR_FIELDS} }}
      }}
    }}
  }}
"""


class CandidatePR(TypedDict):
    number: int
    title: str
    head_ref_name: str
    state: str  # "OPEN" | "MERGED"
    merged: bool
    merged_at: str | None
    is_draft: bool


def _to_candidate(pr: dict) -> CandidatePR:
    return {
        "number": pr["number"],
        "title": pr["title"],
        "head_ref_name": pr["headRefName"],
        "state": pr["state"],
        "merged": pr["state"] == "MERGED",
        "merged_at": pr.get("mergedAt"),
        "is_draft": pr["isDraft"],
    }


def fetch_candidate_prs(client: GitHubClient, now: datetime | None = None) -> list[CandidatePR]:
    """A bounded, repo-wide pool of open PRs plus PRs merged in the last
    FUZZY_CANDIDATE_LOOKBACK_DAYS days - one query per run, not per issue.
    This is the search space the fuzzy matcher compares each unmatched issue
    against; it is not itself evidence for any one issue. Carries full PR
    state (not just title/branch) so a fuzzy match to a merged PR is
    distinguishable from a match to one still open.
    """
    now = now or datetime.now(timezone.utc)
    data = client.query(_QUERY, {"owner": REPO_OWNER, "name": REPO_NAME, "limit": FUZZY_CANDIDATE_LIMIT})
    repository = data.get("repository")
    if not repository:
        return []

    cutoff = now - timedelta(days=FUZZY_CANDIDATE_LOOKBACK_DAYS)
    recently_merged = [
        pr for pr in repository["merged"]["nodes"] if pr.get("mergedAt") and datetime.fromisoformat(pr["mergedAt"]) >= cutoff
    ]

    seen: set[int] = set()
    candidates: list[CandidatePR] = []
    for pr in [*repository["open"]["nodes"], *recently_merged]:
        candidate = _to_candidate(pr)
        if candidate["number"] in seen:
            continue
        seen.add(candidate["number"])
        candidates.append(candidate)

    return candidates
