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

    # A circuit-broken run stops writing entirely (plan: "stop writing"),
    # not just its exit code - any decision reached before the breaker
    # tripped still describes work that was never actually posted/mutated.
    failed_issue_numbers: set[int] = set()
    if not result["circuit_broken"]:
        for issue in result["processed"]:
            decision = issue["decision"]
            if issue["skipped"] or not should_comment(decision):
                continue

            try:
                ctx = CommentContext(run_id=run_id, evidence_hash=issue["evidence_hash"], logs_url=logs_url, now=now, dry_run=dry_run)
                body = build_comment_body(decision, issue["evidence"], ctx)
                post_comment(github_client, issue["issue_node_id"], body)

                if not dry_run:
                    mutate(github_client, issue["evidence"]["item_id"], issue["issue_node_id"], decision, issue["evidence"]["current_status"])
            except Exception as error:  # one issue's write failure must not lose every other issue's already-persisted state
                failed_issue_numbers.add(issue["issue_number"])
                print(f"issue #{issue['issue_number']}: write failed: {error}", file=sys.stderr)

    # The run log is the idempotency source of truth for "unchanged evidence"
    # - an entry may only count as seen once its write actually happened. A
    # dry run writes nothing for real; a circuit-broken run wrote nothing at
    # all; a per-issue failure above means that one issue's write didn't
    # happen either. In every one of those cases the entry must be dropped,
    # or the next run silently skips work that was never actually done.
    writes_are_real = not dry_run and not result["circuit_broken"]
    run_log = [
        entry
        for entry in result["run_log"]
        if entry["run_id"] != run_id or (writes_are_real and entry["issue_number"] not in failed_issue_numbers)
    ]

    save_json(LEASES_PATH, result["lease_state"])
    save_json(RUNLOG_PATH, run_log)

    summary = build_summary(result["processed"])
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if summary and webhook_url:
        post_summary(webhook_url, summary)

    print(f"run {run_id}: processed {len(result['processed'])}, failed {len(result['failed'])}, circuit_broken {result['circuit_broken']}")
    return 1 if result["circuit_broken"] else 0


if __name__ == "__main__":
    sys.exit(main())
