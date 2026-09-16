"""Prompt text for the four reasoning spokes in reasoning.py, kept separate
so wording can be iterated on without touching the API-call plumbing. Each
builder takes only the narrow facts its spoke needs - never a full Evidence
or LinkedPR - to keep prompts small and prevent drift between what's sent
and what's documented here.
"""
from __future__ import annotations

import json
from datetime import datetime

from issue_reconciler.types import LinkedPR


def build_completion_prompt(issue_title: str, linked_prs: list[LinkedPR]) -> str:
    prs = [{"number": pr["number"], "title": pr["title"], "merged": pr["merged"]} for pr in linked_prs]
    return (
        f"Issue: {issue_title}\n\nLinked pull requests: {json.dumps(prs)}\n\n"
        "Not every linked PR necessarily works on this issue - a PR can reference an issue number "
        "in passing, or as part of unrelated cleanup, without actually implementing it. "
        "First decide which of these PRs, if any, actually work toward resolving this issue. "
        "Then, based only on those relevant PRs, judge whether the issue is fully resolved, or only "
        "partially (e.g. one of several needed changes), or not resolved at all if none are relevant. "
        "Judge from the titles alone."
    )


def build_activity_prompt(issue_title: str, pr: LinkedPR, now: datetime) -> str:
    days_since_update = (now - datetime.fromisoformat(pr["updated_at"])).days if pr["updated_at"] else None
    facts = {"number": pr["number"], "title": pr["title"], "days_since_last_update": days_since_update, "review_decision": pr["review_decision"]}
    return (
        f"Issue: {issue_title}\n\nOpen pull request: {json.dumps(facts)}\n\n"
        "Judge whether this PR is still active, blocked (e.g. changes requested and not yet addressed), "
        "or abandoned (no meaningful activity in a long time)."
    )


def build_reference_prompt(issue_title: str, pr: LinkedPR) -> str:
    return (
        f"Issue: {issue_title}\nLinked PR: {pr['title']}\n\n"
        "Does the PR's title suggest it actually addresses this issue, or does it look unrelated - "
        "as if it references the wrong issue number by mistake?"
    )


def build_stale_prompt(issue_title: str, linked_prs: list[LinkedPR]) -> str:
    prs = [{"number": pr["number"], "title": pr["title"], "state": pr["state"], "merged_at": pr["merged_at"]} for pr in linked_prs]
    return (
        f"Issue: {issue_title}\n\nLinked pull requests: {json.dumps(prs)}\n\n"
        "Has an earlier PR been superseded by a later one that solves the problem differently, rather "
        "than building on it? Answer superseded=true only if a later PR replaces an earlier approach entirely."
    )
