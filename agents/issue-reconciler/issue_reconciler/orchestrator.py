"""The hub: selects in-scope issues, fans out read-only evidence gathering,
runs the policy engine, and returns planned decisions. It never mutates
GitHub - see plan hard constraint #4, "one writer" (writers.py).
This module is that boundary: everything before it is read-only, everything
after it is the sole write path.

Concurrency uses real OS threads (ThreadPoolExecutor), not asyncio - the
GitHub/Anthropic clients here are synchronous. Unlike a single-threaded
event loop, that means shared mutable state (leases, the run log, the model
call counter, the circuit breaker) can genuinely race between threads, so
all of it lives behind one lock. Only the network calls themselves run
outside the lock.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TypedDict

import anthropic

from issue_reconciler.client import GitHubClient
from issue_reconciler.config import (
    IGNORE_LABEL,
    LEASE_TTL_SECONDS,
    MAX_CONCURRENCY,
    MODEL_CALL_CAP_PER_RUN,
    PROJECT_ID,
)
from issue_reconciler.fuzzy import match_issue_to_prs
from issue_reconciler.github import (
    CandidatePR,
    fetch_board_items,
    fetch_candidate_prs,
    fetch_linked_prs,
    fetch_open_issues,
    gather_board_history,
    gather_openspec_proposals,
)
from issue_reconciler.hashing import hash_evidence
from issue_reconciler.rules import DEFAULT_FUZZY_CONFIDENCE_THRESHOLD, decide_action
from issue_reconciler.state import (
    LeaseState,
    RunLogEntry,
    acquire_lease,
    find_latest_for_issue,
    release_lease,
)
from issue_reconciler.types import Decision, Evidence, LinkedPR


class ProcessedIssue(TypedDict):
    issue_number: int
    issue_node_id: str
    decision: Decision
    evidence: Evidence | None
    evidence_hash: str
    skipped: str | None  # "leased" | "unchanged-evidence" | None


class FailedIssue(TypedDict):
    issue_number: int
    error: str


class OrchestratorResult(TypedDict):
    processed: list[ProcessedIssue]
    failed: list[FailedIssue]
    lease_state: LeaseState
    run_log: list[RunLogEntry]
    circuit_broken: bool


def validate_board_config(client: GitHubClient) -> None:
    """Fails loudly if the configured project no longer resolves, rather
    than silently processing zero issues (see plan Reliability: "Startup
    validation").
    """
    data = client.query("query ValidateProject($projectId: ID!) { node(id: $projectId) { id } }", {"projectId": PROJECT_ID})
    if not data.get("node"):
        raise RuntimeError(f"Configured PROJECT_ID {PROJECT_ID} no longer resolves to a project")


def _to_linked_pr(pr_number: int, confidence: float, candidate_pool: list[CandidatePR]) -> LinkedPR:
    # Fuzzy matching only ever runs against the candidate pool, so the
    # source record is guaranteed present - carry its real state through
    # rather than assuming OPEN, since the pool includes recently-merged
    # PRs too and the policy engine's set_done/set_in_progress rules depend
    # on this being accurate.
    candidate = next(c for c in candidate_pool if c["number"] == pr_number)
    return {
        "number": candidate["number"],
        "title": candidate["title"],
        "head_ref_name": candidate["head_ref_name"],
        "state": candidate["state"],
        "merged": candidate["merged"],
        "merged_at": candidate["merged_at"],
        "is_draft": candidate["is_draft"],
        "match_source": "fuzzy",
        "confidence": confidence,
    }


class _RunState:
    """All state shared across worker threads, guarded by one lock. Methods
    are short, synchronous critical sections - the network calls that
    surround them in run_one() happen outside the lock.
    """

    def __init__(self, lease_state: LeaseState, run_log: list[RunLogEntry]):
        self._lock = threading.Lock()
        self.lease_state = lease_state
        self.run_log = run_log
        self.model_calls_made = 0
        self.circuit_broken = False
        self.processed: list[ProcessedIssue] = []
        self.failed: list[FailedIssue] = []

    def is_circuit_broken(self) -> bool:
        with self._lock:
            return self.circuit_broken

    def try_acquire_lease(self, issue_number: int, ttl_seconds: int, now: datetime) -> bool:
        with self._lock:
            leased = acquire_lease(self.lease_state, issue_number, ttl_seconds, now)
            if leased is None:
                return False
            self.lease_state = leased
            return True

    def release_lease(self, issue_number: int) -> None:
        with self._lock:
            self.lease_state = release_lease(self.lease_state, issue_number)

    def find_latest_evidence_hash(self, issue_number: int) -> str | None:
        with self._lock:
            entry = find_latest_for_issue(self.run_log, issue_number)
            return entry["evidence_hash"] if entry else None

    def try_reserve_model_call(self, cap: int) -> bool:
        with self._lock:
            if self.model_calls_made >= cap:
                self.circuit_broken = True
                return False
            self.model_calls_made += 1
            return True

    def record_decision(self, run_id: str, issue_number: int, decision: Decision, evidence_hash: str, now: datetime) -> None:
        with self._lock:
            self.run_log = [
                *self.run_log,
                {
                    "run_id": run_id,
                    "issue_number": issue_number,
                    "decision": decision["action"],
                    "reason": decision["reason"],
                    "evidence_hash": evidence_hash,
                    "timestamp": now.isoformat(),
                },
            ]

    def add_processed(self, item: ProcessedIssue) -> None:
        with self._lock:
            self.processed.append(item)

    def add_failed(self, item: FailedIssue, error_rate_threshold: float, total: int) -> None:
        with self._lock:
            self.failed.append(item)
            if len(self.failed) / total > error_rate_threshold:
                self.circuit_broken = True


def run(
    *,
    github_client: GitHubClient,
    anthropic_client: anthropic.Anthropic,
    run_id: str,
    lease_state: LeaseState,
    run_log: list[RunLogEntry],
    now: datetime | None = None,
    fuzzy_confidence_threshold: float | None = None,
    max_concurrency: int = MAX_CONCURRENCY,
    model_call_cap: int = MODEL_CALL_CAP_PER_RUN,
    circuit_breaker_error_rate: float = 0.2,
) -> OrchestratorResult:
    now = now or datetime.now(timezone.utc)

    board_items = fetch_board_items(github_client)
    open_issues = fetch_open_issues(github_client)
    issues_by_number = {i["number"]: i for i in open_issues}

    in_scope = [item for item in board_items if item["issue_number"] in issues_by_number]
    issue_numbers = [item["issue_number"] for item in in_scope]

    linked_prs_by_issue = fetch_linked_prs(github_client, issue_numbers)
    board_history_by_issue = gather_board_history(github_client, issue_numbers, now)
    openspec_by_issue = gather_openspec_proposals(github_client)
    candidate_pool = fetch_candidate_prs(github_client, now)

    state = _RunState(lease_state, run_log)

    def process_one(item) -> None:
        if state.is_circuit_broken():
            return

        issue_number = item["issue_number"]
        issue_node_id = issues_by_number[issue_number]["id"]

        if not state.try_acquire_lease(issue_number, LEASE_TTL_SECONDS, now):
            state.add_processed(
                {
                    "issue_number": issue_number,
                    "issue_node_id": issue_node_id,
                    "decision": {"action": "noop", "reason": "already leased"},
                    "evidence": None,
                    "evidence_hash": "",
                    "skipped": "leased",
                }
            )
            return

        try:
            issue_meta = issues_by_number[issue_number]
            history = board_history_by_issue.get(issue_number, {"last_status_actor": None, "last_status_at": None, "transition_count": 0})
            linked_prs = linked_prs_by_issue.get(issue_number, [])

            evidence: Evidence = {
                "issue_number": issue_number,
                "item_id": item["item_id"],
                "current_status": item["status"],
                "has_ignore_label": IGNORE_LABEL in issue_meta["labels"],
                "linked_prs": linked_prs,
                "open_spec_proposals": openspec_by_issue.get(issue_number, []),
                "last_status_actor": history["last_status_actor"],
                "last_status_at": history["last_status_at"],
                "transition_count": history["transition_count"],
            }

            hash_before_matching = hash_evidence(evidence)
            if state.find_latest_evidence_hash(issue_number) == hash_before_matching:
                state.add_processed(
                    {
                        "issue_number": issue_number,
                        "issue_node_id": issue_node_id,
                        "decision": {"action": "noop", "reason": "unchanged evidence"},
                        "evidence": evidence,
                        "evidence_hash": hash_before_matching,
                        "skipped": "unchanged-evidence",
                    }
                )
                return

            # Fuzzy matching only runs when there is no explicit reference -
            # an ignored issue skips it too, since its decision is 'noop'
            # regardless of what the matcher would say.
            if not linked_prs and not evidence["has_ignore_label"] and candidate_pool:
                if not state.try_reserve_model_call(model_call_cap):
                    return
                matches = match_issue_to_prs(
                    anthropic_client, {"number": issue_number, "title": issue_meta["title"]}, candidate_pool
                )
                linked_prs = [_to_linked_pr(m["pr_number"], m["confidence"], candidate_pool) for m in matches]
                evidence["linked_prs"] = linked_prs

            evidence_hash = hash_evidence(evidence)
            decision = decide_action(
                evidence,
                fuzzy_confidence_threshold=fuzzy_confidence_threshold or DEFAULT_FUZZY_CONFIDENCE_THRESHOLD,
                now=now,
            )

            state.record_decision(run_id, issue_number, decision, evidence_hash, now)
            state.add_processed(
                {
                    "issue_number": issue_number,
                    "issue_node_id": issue_node_id,
                    "decision": decision,
                    "evidence": evidence,
                    "evidence_hash": evidence_hash,
                    "skipped": None,
                }
            )
        except Exception as error:  # any per-issue failure feeds the circuit breaker, never aborts the batch
            state.add_failed(
                {"issue_number": issue_number, "error": str(error)}, circuit_breaker_error_rate, len(in_scope)
            )
        finally:
            state.release_lease(issue_number)

    if in_scope:
        with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
            list(executor.map(process_one, in_scope))

    return {
        "processed": state.processed,
        "failed": state.failed,
        "lease_state": state.lease_state,
        "run_log": state.run_log,
        "circuit_broken": state.circuit_broken,
    }
