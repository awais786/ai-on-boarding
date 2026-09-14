"""Phase 6: the actual board/issue mutations, gated behind dry_run in
apply_decision(). Comment-first, mutate-second - see writers/comment.py and
plan "Ordering": status, then close, since a failed close still leaves the
board correct for the next run to reconcile.
"""
from __future__ import annotations

from issue_reconciler.api.client import GitHubClient
from issue_reconciler.config import (
    NEEDS_TRIAGE_LABEL,
    PROJECT_ID,
    REPO_NAME,
    REPO_OWNER,
    STATUS_FIELD_ID,
    STATUS_OPTIONS,
)
from issue_reconciler.types import Decision

_SET_STATUS = """
  mutation SetStatus($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
    updateProjectV2ItemFieldValue(input: {
      projectId: $projectId, itemId: $itemId, fieldId: $fieldId,
      value: { singleSelectOptionId: $optionId }
    }) { projectV2Item { id } }
  }
"""

_CURRENT_STATUS = """
  query CurrentStatus($itemId: ID!) {
    node(id: $itemId) {
      ... on ProjectV2Item {
        status: fieldValueByName(name: "Status") {
          ... on ProjectV2ItemFieldSingleSelectValue { name }
        }
      }
    }
  }
"""

_CLOSE_ISSUE = "mutation CloseIssue($issueId: ID!) { closeIssue(input: { issueId: $issueId }) { issue { id } } }"

_FIND_LABEL = """
  query FindLabel($owner: String!, $name: String!, $label: String!) {
    repository(owner: $owner, name: $name) { label(name: $label) { id } }
  }
"""

_ADD_LABEL = "mutation AddLabel($labelableId: ID!, $labelId: ID!) { addLabelsToLabelable(input: { labelableId: $labelableId, labelIds: [$labelId] }) { clientMutationId } }"


def current_status(client: GitHubClient, item_id: str) -> str | None:
    """Read-then-write tight: Projects v2 has no compare-and-set, so callers
    re-check this immediately before mutating and abort if it moved.
    """
    data = client.query(_CURRENT_STATUS, {"itemId": item_id})
    status = (data.get("node") or {}).get("status")
    return status["name"] if status else None


def set_status(client: GitHubClient, item_id: str, status_name: str) -> None:
    client.query(
        _SET_STATUS,
        {"projectId": PROJECT_ID, "itemId": item_id, "fieldId": STATUS_FIELD_ID, "optionId": STATUS_OPTIONS[status_name]},
    )


def close_issue(client: GitHubClient, issue_node_id: str) -> None:
    client.query(_CLOSE_ISSUE, {"issueId": issue_node_id})


def add_needs_triage_label(client: GitHubClient, issue_node_id: str) -> None:
    data = client.query(_FIND_LABEL, {"owner": REPO_OWNER, "name": REPO_NAME, "label": NEEDS_TRIAGE_LABEL})
    label_id = (data.get("repository") or {}).get("label", {}).get("id")
    if not label_id:
        raise RuntimeError(f"label {NEEDS_TRIAGE_LABEL!r} does not exist in {REPO_OWNER}/{REPO_NAME}")
    client.query(_ADD_LABEL, {"labelableId": issue_node_id, "labelId": label_id})


def mutate(client: GitHubClient, item_id: str, issue_node_id: str, decision: Decision, expected_status: str | None) -> None:
    """Applies the one mutation a decision calls for. Skipped entirely if
    the board status moved since evidence was gathered (see current_status).
    """
    if current_status(client, item_id) != expected_status:
        return

    if decision["action"] == "set_done":
        set_status(client, item_id, "Done")
        try:
            close_issue(client, issue_node_id)
        except Exception:  # noqa: S110 - board is already correct; the next run reconciles the issue state
            pass
    elif decision["action"] == "set_in_progress":
        set_status(client, item_id, "In Progress")
    elif decision["action"] == "flag":
        add_needs_triage_label(client, issue_node_id)
