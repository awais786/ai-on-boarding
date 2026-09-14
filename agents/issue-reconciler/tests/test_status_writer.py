from __future__ import annotations

from support import make_routed_client

from issue_reconciler.writers.status import mutate


def test_set_done_updates_status_then_closes_the_issue():
    client, calls = make_routed_client(
        [
            ("CurrentStatus", {"node": {"status": {"name": "In Progress"}}}),
            ("SetStatus", {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_1"}}}),
            ("CloseIssue", {"closeIssue": {"issue": {"id": "I_1"}}}),
        ]
    )

    mutate(client, "PVTI_1", "I_1", {"action": "set_done", "reason": "x"}, expected_status="In Progress")

    assert len(calls) == 3
    assert "SetStatus" in calls[1]["query"]
    assert "CloseIssue" in calls[2]["query"]


def test_flag_looks_up_the_label_then_adds_it():
    client, calls = make_routed_client(
        [
            ("CurrentStatus", {"node": {"status": {"name": "Todo"}}}),
            ("FindLabel", {"repository": {"label": {"id": "LA_1"}}}),
            ("AddLabel", {"addLabelsToLabelable": {"clientMutationId": None}}),
        ]
    )

    mutate(client, "PVTI_1", "I_1", {"action": "flag", "reason": "mixed PR states"}, expected_status="Todo")

    assert len(calls) == 3


def test_mutation_is_skipped_if_status_moved_since_evidence_was_gathered():
    client, calls = make_routed_client([("CurrentStatus", {"node": {"status": {"name": "Done"}}})])

    mutate(client, "PVTI_1", "I_1", {"action": "set_in_progress", "reason": "x"}, expected_status="Todo")

    assert len(calls) == 1  # only the re-read; no mutation followed
