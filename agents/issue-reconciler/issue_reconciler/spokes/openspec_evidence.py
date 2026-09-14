from __future__ import annotations

import re

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.api.fetchers.repo import fetch_openspec_changes

_ISSUE_REF_RE = re.compile(r"#(\d+)")


def gather_openspec_proposals(client: GitHubClient) -> dict[int, list[str]]:
    """Correlates each in-flight OpenSpec proposal to the issue number(s) it
    references (e.g. "Closes #12"), returning issue number -> change names.
    One repo-wide fetch, not one per issue - the proposal list is small and
    shared across the whole batch.
    """
    changes = fetch_openspec_changes(client)
    by_issue: dict[int, list[str]] = {}

    for change in changes:
        referenced = {int(n) for n in _ISSUE_REF_RE.findall(change["proposal_text"])}
        for issue_number in referenced:
            by_issue.setdefault(issue_number, []).append(change["name"])

    return by_issue
