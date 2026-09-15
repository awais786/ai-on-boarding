"""Shape of evidence in, decision out - the contract every layer agrees on.
Plain TypedDicts, not classes: these values are built from JSON (GraphQL
responses, fixtures, the model's structured output) and compared in tests as
plain dicts, so there is nothing a class would buy here.
"""
from __future__ import annotations

from typing import Literal, TypedDict


class LinkedPR(TypedDict):
    number: int
    title: str
    state: Literal["OPEN", "CLOSED", "MERGED"]
    merged: bool
    merged_at: str | None
    is_draft: bool
    head_ref_name: str
    updated_at: str | None  # last commit/push activity - feeds the activity-check spoke
    review_decision: str | None  # APPROVED / CHANGES_REQUESTED / REVIEW_REQUIRED / None


class Evidence(TypedDict):
    issue_number: int
    item_id: str  # project item ID
    current_status: str | None
    has_ignore_label: bool
    linked_prs: list[LinkedPR]
    open_spec_proposals: list[str]
    last_status_actor: str | None
    last_status_at: str | None
    transition_count: int  # agent flips in last 7 days


class Decision(TypedDict):
    action: Literal["set_done", "set_in_progress", "flag", "noop"]
    reason: str
