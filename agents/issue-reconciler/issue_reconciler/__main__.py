"""Entrypoint: run orchestrator.run(), then the writer, per issue.
`python -m issue_reconciler [--no-dry-run]` (default: dry-run on).
State (leases, run log) lives in JSON files next to wherever this runs -
in Actions that's the repo checkout, committed back by the workflow step
after this exits (see plan Reliability: "a committed JSON file").
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from issue_reconciler import orchestrator
from issue_reconciler.client import GitHubClient
from issue_reconciler.slack import build_summary, post_summary
from issue_reconciler.state import load_lease_state, load_run_log, save_json
from issue_reconciler.writers import (
    CommentContext,
    build_comment_body,
    mutate,
    post_comment,
    should_comment,
)

STATE_DIR = Path(os.environ.get("RECONCILER_STATE_DIR", "."))
LEASES_PATH = STATE_DIR / "leases.json"
RUNLOG_PATH = STATE_DIR / "runlog.json"


def main() -> int:
    dry_run = "--no-dry-run" not in sys.argv

    github_client = GitHubClient(os.environ["BOARD_TOKEN"])
    anthropic_client = anthropic.Anthropic()
    run_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    logs_url = os.environ.get("RECONCILER_LOGS_URL", "")

    orchestrator.validate_board_config(github_client)

    result = orchestrator.run(
        github_client=github_client,
        anthropic_client=anthropic_client,
        run_id=run_id,
        lease_state=load_lease_state(LEASES_PATH),
        run_log=load_run_log(RUNLOG_PATH),
        now=now,
    )

    for issue in result["processed"]:
        decision = issue["decision"]
        if issue["skipped"] or not should_comment(decision):
            continue

        ctx = CommentContext(run_id=run_id, evidence_hash=issue["evidence_hash"], logs_url=logs_url, now=now, dry_run=dry_run)
        body = build_comment_body(decision, issue["evidence"], ctx)
        post_comment(github_client, issue["issue_node_id"], body)

        if not dry_run:
            mutate(github_client, issue["evidence"]["item_id"], issue["issue_node_id"], decision, issue["evidence"]["current_status"])

    summary = build_summary(result["processed"])
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if summary and webhook_url:
        post_summary(webhook_url, summary)

    save_json(LEASES_PATH, result["lease_state"])
    save_json(RUNLOG_PATH, result["run_log"])

    print(f"run {run_id}: processed {len(result['processed'])}, failed {len(result['failed'])}, circuit_broken {result['circuit_broken']}")
    return 1 if result["circuit_broken"] else 0


if __name__ == "__main__":
    sys.exit(main())
