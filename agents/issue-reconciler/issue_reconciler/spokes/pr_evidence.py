from __future__ import annotations

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.api.fetchers.prs import fetch_linked_prs
from issue_reconciler.types import LinkedPR


def gather_pr_links(client: GitHubClient, issue_numbers: list[int]) -> dict[int, list[LinkedPR]]:
    """Read-only: returns evidence (explicit PR links per issue), never a
    decision. The hub's policy engine is the only place that turns this
    into an action.
    """
    return fetch_linked_prs(client, issue_numbers)
