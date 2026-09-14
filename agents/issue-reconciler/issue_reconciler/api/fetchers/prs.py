from __future__ import annotations

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.config import REPO_NAME, REPO_OWNER
from issue_reconciler.types import LinkedPR

_BATCH_SIZE = 50

_PR_FIELDS = """
  __typename
  ... on PullRequest {
    number
    title
    state
    merged
    mergedAt
    isDraft
    headRefName
  }
"""


def _build_query(issue_numbers: list[int]) -> str:
    aliases = "\n".join(
        f"""
    issue_{i}: issue(number: {n}) {{
      timelineItems(first: 50, itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT]) {{
        nodes {{
          __typename
          ... on CrossReferencedEvent {{
            willCloseTarget
            source {{ {_PR_FIELDS} }}
          }}
          ... on ConnectedEvent {{
            subject {{ {_PR_FIELDS} }}
          }}
        }}
      }}
    }}"""
        for i, n in enumerate(issue_numbers)
    )
    return f"""query LinkedPRs($owner: String!, $name: String!) {{
    repository(owner: $owner, name: $name) {{ {aliases} }}
  }}"""


def _to_linked_pr(pr: dict) -> LinkedPR:
    return {
        "number": pr["number"],
        "title": pr.get("title", ""),
        "state": pr.get("state", "OPEN"),
        "merged": pr.get("merged", False),
        "merged_at": pr.get("mergedAt"),
        "is_draft": pr.get("isDraft", False),
        "head_ref_name": pr.get("headRefName", ""),
        "match_source": "explicit",
        "confidence": 1.0,
    }


def fetch_linked_prs(client: GitHubClient, issue_numbers: list[int]) -> dict[int, list[LinkedPR]]:
    """Fetches explicit PR references (closing keywords, manually linked) for
    a batch of issues in a single request via aliased sub-queries, per the
    plan's "single GraphQL query per issue batch, not per issue" constraint.
    Fuzzy matching for issues with no explicit reference happens later, in
    the matcher, over PRs this fetcher does not return.
    """
    result: dict[int, list[LinkedPR]] = {}

    for start in range(0, len(issue_numbers), _BATCH_SIZE):
        batch = issue_numbers[start : start + _BATCH_SIZE]
        data = client.query(_build_query(batch), {"owner": REPO_OWNER, "name": REPO_NAME})
        repository = data.get("repository") or {}

        for i, issue_number in enumerate(batch):
            node = repository.get(f"issue_{i}")
            prs: list[LinkedPR] = []
            seen: set[int] = set()

            for item in (node or {}).get("timelineItems", {}).get("nodes", []):
                raw = None
                if item.get("__typename") == "CrossReferencedEvent":
                    source = item.get("source") or {}
                    if item.get("willCloseTarget") and source.get("__typename") == "PullRequest":
                        raw = source
                elif item.get("__typename") == "ConnectedEvent":
                    subject = item.get("subject") or {}
                    if subject.get("__typename") == "PullRequest":
                        raw = subject

                if raw is None:
                    continue
                pr = _to_linked_pr(raw)
                if pr["number"] not in seen:
                    seen.add(pr["number"])
                    prs.append(pr)

            result[issue_number] = prs

    return result
