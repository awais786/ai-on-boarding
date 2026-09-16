"""Posts one run-level summary to Slack after every issue is processed and
written - not per issue. Mirrors the "noop never comments" rule: a run that
changed nothing posts nothing, so a daily cron doesn't become daily noise.
"""
from __future__ import annotations

import requests

from issue_reconciler.config import REPO_NAME, REPO_OWNER

_ACTION_LABELS = {"set_done": "Done", "set_in_progress": "In progress", "flag": "Needs review"}


def _issue_link(issue_number: int) -> str:
    return f"<https://github.com/{REPO_OWNER}/{REPO_NAME}/issues/{issue_number}|#{issue_number}>"


def _pr_link(pr_number: int) -> str:
    return f"<https://github.com/{REPO_OWNER}/{REPO_NAME}/pull/{pr_number}|#{pr_number}>"


def _relevant_pr_links(action: str, evidence: dict | None) -> list[str]:
    """The PR(s) worth showing next to this decision - the merged one for a
    close, the open one for in-progress, every linked PR for a flag (the
    human reviewing it needs to see the whole ambiguous set).
    """
    if not evidence:
        return []
    linked_prs = evidence["linked_prs"]
    if action == "set_done":
        pr = next((pr for pr in linked_prs if pr["merged"]), None)
        return [_pr_link(pr["number"])] if pr else []
    if action == "set_in_progress":
        pr = next((pr for pr in linked_prs if pr["state"] == "OPEN"), None)
        return [_pr_link(pr["number"])] if pr else []
    if action == "flag":
        return [_pr_link(pr["number"]) for pr in linked_prs]
    return []


def build_summary(processed: list[dict]) -> str | None:
    lines = []
    for p in processed:
        action = p["decision"]["action"]
        if p["skipped"] or action == "noop":
            continue
        pr_links = _relevant_pr_links(action, p.get("evidence"))
        pr_note = f" (PR {', '.join(pr_links)})" if pr_links else ""
        lines.append(f"{_ACTION_LABELS[action]} — {_issue_link(p['issue_number'])}: {p['decision']['reason']}{pr_note}")

    if not lines:
        return None

    # "Untouched" means no linked PR *and* nothing else happened either (e.g.
    # not an OpenSpec-proposal-driven set_in_progress with no PR yet) -
    # otherwise an issue could be counted as both changed and untouched.
    untouched = sum(1 for p in processed if p["decision"]["action"] == "noop" and p.get("evidence") and not p["evidence"]["linked_prs"])
    header = f"Issue reconciler ran on {len(processed)} issue(s), {len(lines)} changed, {untouched} untouched (no linked PR):"
    return f"{header}\n" + "\n".join(lines)


def post_summary(webhook_url: str, text: str) -> None:
    response = requests.post(webhook_url, json={"text": text}, timeout=10)
    response.raise_for_status()
