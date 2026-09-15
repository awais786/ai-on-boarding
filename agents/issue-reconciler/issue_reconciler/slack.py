"""Posts one run-level summary to Slack after every issue is processed and
written - not per issue. Mirrors the "noop never comments" rule: a run that
changed nothing posts nothing, so a daily cron doesn't become daily noise.
"""
from __future__ import annotations

import requests


def build_summary(processed: list[dict]) -> str | None:
    lines = [f"#{p['issue_number']}: {p['decision']['action']} — {p['decision']['reason']}" for p in processed if not p["skipped"] and p["decision"]["action"] != "noop"]
    if not lines:
        return None
    return f"Issue reconciler ran on {len(processed)} issue(s), {len(lines)} changed:\n" + "\n".join(lines)


def post_summary(webhook_url: str, text: str) -> None:
    response = requests.post(webhook_url, json={"text": text}, timeout=10)
    response.raise_for_status()
