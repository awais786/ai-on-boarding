from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.fingerprint import build_fingerprint
from issue_reconciler.types import Decision, Evidence, LinkedPR

_ADD_COMMENT = """
  mutation AddComment($subjectId: ID!, $body: String!) {
    addComment(input: { subjectId: $subjectId, body: $body }) {
      commentEdge { node { id } }
    }
  }
"""


@dataclass
class CommentContext:
    run_id: str
    evidence_hash: str
    logs_url: str
    now: datetime
    dry_run: bool


def _describe_pr(pr: LinkedPR) -> str:
    if pr["match_source"] == "explicit":
        match = "closing reference in PR body"
    else:
        match = f"title similarity (confidence {pr['confidence']:.2f}). No explicit reference found"
    return f"Matched via: {match}."


def _evidence_line(decision: Decision, evidence: Evidence) -> str:
    merged = next((pr for pr in evidence["linked_prs"] if pr["merged"]), None)
    open_pr = next((pr for pr in evidence["linked_prs"] if pr["state"] == "OPEN"), None)

    action = decision["action"]
    if action == "set_done":
        date = merged["merged_at"][:10] if merged["merged_at"] else "unknown date"
        return f"Done — PR #{merged['number']} merged {date}.\n{_describe_pr(merged)}"

    if action == "set_in_progress":
        if open_pr:
            return f"In progress — PR #{open_pr['number']} open.\n{_describe_pr(open_pr)}"
        proposal = evidence["open_spec_proposals"][0]
        return f"In progress — OpenSpec proposal `{proposal}` in flight. No PR yet."

    if action == "flag":
        lines = [f"Needs a human — {decision['reason']}."]
        if evidence["linked_prs"]:
            parts = []
            for pr in evidence["linked_prs"]:
                extra = f", confidence {pr['confidence']:.2f}" if pr["match_source"] == "fuzzy" else ""
                parts.append(f"#{pr['number']} ({pr['state']}{extra})")
            lines.append(f"Linked PRs: {', '.join(parts)}.")
        lines.append("If this is wrong, add `agent:ignore` and reopen.")
        return "\n".join(lines)

    raise ValueError("noop decisions never produce a comment")


def should_comment(decision: Decision) -> bool:
    """noop never comments - see plan "Commenting": a 30-minute cron must
    not turn every issue into a wall of "still nothing to report".
    """
    return decision["action"] != "noop"


def build_comment_body(decision: Decision, evidence: Evidence, ctx: CommentContext) -> str:
    prefix = "**[dry run]** Would report:\n\n" if ctx.dry_run else ""
    body = _evidence_line(decision, evidence)
    run_line = f"Run: {ctx.now.isoformat()} · [logs]({ctx.logs_url})"

    # A dry run never mutates status, so its comment must not be mistaken
    # for a real transition on a later run - board_history parses
    # fingerprints to recover "who last touched status" (see fingerprint.py),
    # and a recognized fingerprint here would inflate transition_count and
    # could even trigger the flapping rule from announcements that changed
    # nothing. parse_fingerprint only matches the literal "v1" marker, so
    # this differently-shaped marker is invisible to it by construction.
    if ctx.dry_run:
        marker = f"<!-- issue-reconciler: dry-run run={ctx.run_id} decision={decision['action']} evidence=sha256:{ctx.evidence_hash} -->"
    else:
        marker = build_fingerprint({"run_id": ctx.run_id, "decision": decision["action"], "evidence_hash": ctx.evidence_hash})

    return f"{prefix}{body}\n{run_line}\n{marker}"


def post_comment(client: GitHubClient, issue_node_id: str, body: str) -> str:
    """The sole write for both real and dry-run decisions - see plan
    "Ordering": comment first, then (a future writer) mutates status. A
    dry run still posts, it just has no status/close mutation to follow.
    Raises on failure (GraphQLError etc.) - the caller aborts the
    transition rather than swallowing it, per "No silent transitions".
    """
    data = client.query(_ADD_COMMENT, {"subjectId": issue_node_id, "body": body})
    return data["addComment"]["commentEdge"]["node"]["id"]
