from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TypedDict

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.api.fetchers.timeline import IssueComment, fetch_issue_comments
from issue_reconciler.config import TRANSITION_LOOKBACK_DAYS
from issue_reconciler.fingerprint import parse_fingerprint
from issue_reconciler.policy.rules import AGENT_ACTOR

_TRANSITION_DECISIONS = {"set_done", "set_in_progress"}


class BoardHistoryEntry(TypedDict):
    last_status_actor: str | None
    last_status_at: str | None
    transition_count: int


def summarize_history(comments: list[IssueComment], now: datetime) -> BoardHistoryEntry:
    """The GitHub API exposes no history of Projects v2 field-value changes,
    so this reconstructs "who last touched status, and when" from the
    agent's own fingerprinted comments (see fingerprint.py) plus ordinary
    human comments as a proxy for recent human attention. The PAT backing
    the agent's writes belongs to a human account, so author login alone
    can't tell the two apart - the fingerprint is what does.
    """
    lookback = timedelta(days=TRANSITION_LOOKBACK_DAYS)
    transition_count = 0
    for comment in comments:
        fp = parse_fingerprint(comment["body"])
        if not fp or fp["decision"] not in _TRANSITION_DECISIONS:
            continue
        if now - datetime.fromisoformat(comment["created_at"]) < lookback:
            transition_count += 1

    if not comments:
        return {"last_status_actor": None, "last_status_at": None, "transition_count": transition_count}

    last = comments[-1]
    last_fingerprint = parse_fingerprint(last["body"])
    return {
        "last_status_actor": AGENT_ACTOR if last_fingerprint else last["author"],
        "last_status_at": last["created_at"],
        "transition_count": transition_count,
    }


def gather_board_history(
    client: GitHubClient, issue_numbers: list[int], now: datetime | None = None
) -> dict[int, BoardHistoryEntry]:
    now = now or datetime.now(timezone.utc)
    comments_by_issue = fetch_issue_comments(client, issue_numbers)
    return {n: summarize_history(comments_by_issue.get(n, []), now) for n in issue_numbers}
