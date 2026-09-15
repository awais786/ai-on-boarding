"""The sole write authority (plan hard constraint #4): builds and posts the
evidence-only comment, then - only on a real (non-dry) run - applies the one
status/close/label mutation the decision calls for. Comment first, mutate
second: if the comment fails, the caller aborts before any mutation runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from issue_reconciler.client import GitHubClient
from issue_reconciler.config import (
    NEEDS_TRIAGE_LABEL,
    PROJECT_ID,
    REPO_NAME,
    REPO_OWNER,
    STATUS_FIELD_ID,
    STATUS_OPTIONS,
)
from issue_reconciler.hashing import build_fingerprint
from issue_reconciler.types import Decision, Evidence

_ADD_COMMENT = "mutation AddComment($subjectId: ID!, $body: String!) { addComment(input: { subjectId: $subjectId, body: $body }) { commentEdge { node { id } } } }"
_SET_STATUS = """
  mutation SetStatus($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
    updateProjectV2ItemFieldValue(input: { projectId: $projectId, itemId: $itemId, fieldId: $fieldId, value: { singleSelectOptionId: $optionId } }) { projectV2Item { id } }
  }
"""
_CURRENT_STATUS = """
  query CurrentStatus($itemId: ID!) {
    node(id: $itemId) { ... on ProjectV2Item { status: fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } } } }
  }
"""
_CLOSE_ISSUE = "mutation CloseIssue($issueId: ID!) { closeIssue(input: { issueId: $issueId }) { issue { id } } }"
_FIND_LABEL = "query FindLabel($owner: String!, $name: String!, $label: String!) { repository(owner: $owner, name: $name) { label(name: $label) { id } } }"
_ADD_LABEL = "mutation AddLabel($labelableId: ID!, $labelId: ID!) { addLabelsToLabelable(input: { labelableId: $labelableId, labelIds: [$labelId] }) { clientMutationId } }"


@dataclass
class CommentContext:
    run_id: str
    evidence_hash: str
    logs_url: str
    now: datetime
    dry_run: bool


def _evidence_line(decision: Decision, evidence: Evidence) -> str:
    merged = next((pr for pr in evidence["linked_prs"] if pr["merged"]), None)
    open_pr = next((pr for pr in evidence["linked_prs"] if pr["state"] == "OPEN"), None)
    action = decision["action"]

    if action == "set_done":
        date = merged["merged_at"][:10] if merged["merged_at"] else "unknown date"
        return f"Done — PR #{merged['number']} merged {date}."

    if action == "set_in_progress":
        if open_pr:
            return f"In progress — PR #{open_pr['number']} open."
        return f"In progress — OpenSpec proposal `{evidence['open_spec_proposals'][0]}` in flight. No PR yet."

    if action == "flag":
        lines = [f"Needs a human — {decision['reason']}."]
        if evidence["linked_prs"]:
            parts = [f"#{pr['number']} ({pr['state']})" for pr in evidence["linked_prs"]]
            lines.append(f"Linked PRs: {', '.join(parts)}.")
        lines.append("If this is wrong, add `agent:ignore` and reopen.")
        return "\n".join(lines)

    raise ValueError("noop decisions never produce a comment")


def should_comment(decision: Decision) -> bool:
    """noop never comments - a 30-minute cron must not turn every quiet
    issue into a wall of "still nothing to report".
    """
    return decision["action"] != "noop"


def build_comment_body(decision: Decision, evidence: Evidence, ctx: CommentContext) -> str:
    prefix = "**[dry run]** Would report:\n\n" if ctx.dry_run else ""
    run_line = f"Run: {ctx.now.isoformat()} · [logs]({ctx.logs_url})"

    # A dry run never mutates status, so its marker must be invisible to
    # parse_fingerprint (github.py's summarize_history) - otherwise a dry
    # run's own announcements would look like real transitions on the next
    # run and could even trigger the flapping rule.
    if ctx.dry_run:
        marker = f"<!-- issue-reconciler: dry-run run={ctx.run_id} decision={decision['action']} evidence=sha256:{ctx.evidence_hash} -->"
    else:
        marker = build_fingerprint({"run_id": ctx.run_id, "decision": decision["action"], "evidence_hash": ctx.evidence_hash})

    return f"{prefix}{_evidence_line(decision, evidence)}\n{run_line}\n{marker}"


def post_comment(client: GitHubClient, issue_node_id: str, body: str) -> str:
    """Raises on failure - the caller aborts the transition rather than
    proceeding silently (plan: "No silent transitions").
    """
    data = client.query(_ADD_COMMENT, {"subjectId": issue_node_id, "body": body})
    return data["addComment"]["commentEdge"]["node"]["id"]


def _current_status(client: GitHubClient, item_id: str) -> str | None:
    status = (client.query(_CURRENT_STATUS, {"itemId": item_id}).get("node") or {}).get("status")
    return status["name"] if status else None


def mutate(client: GitHubClient, item_id: str, issue_node_id: str, decision: Decision, expected_status: str | None) -> None:
    """The one status/close/label mutation `decision` calls for - skipped
    entirely if the board status moved since evidence was gathered
    (Projects v2 has no compare-and-set, so this is the read-then-write
    check). set_done sets status before closing: if the close fails, the
    board is already correct and the next run reconciles the issue.
    """
    if _current_status(client, item_id) != expected_status:
        return

    if decision["action"] == "set_done":
        client.query(_SET_STATUS, {"projectId": PROJECT_ID, "itemId": item_id, "fieldId": STATUS_FIELD_ID, "optionId": STATUS_OPTIONS["Done"]})
        try:
            client.query(_CLOSE_ISSUE, {"issueId": issue_node_id})
        except Exception:  # noqa: S110 - board is already correct; the next run reconciles the issue
            pass
    elif decision["action"] == "set_in_progress":
        client.query(_SET_STATUS, {"projectId": PROJECT_ID, "itemId": item_id, "fieldId": STATUS_FIELD_ID, "optionId": STATUS_OPTIONS["In Progress"]})
    elif decision["action"] == "flag":
        label_id = (client.query(_FIND_LABEL, {"owner": REPO_OWNER, "name": REPO_NAME, "label": NEEDS_TRIAGE_LABEL}).get("repository") or {}).get("label", {}).get("id")
        if not label_id:
            raise RuntimeError(f"label {NEEDS_TRIAGE_LABEL!r} does not exist in {REPO_OWNER}/{REPO_NAME}")
        client.query(_ADD_LABEL, {"labelableId": issue_node_id, "labelId": label_id})
