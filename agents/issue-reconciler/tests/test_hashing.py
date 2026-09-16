from __future__ import annotations

from datetime import datetime, timezone

from issue_reconciler.hashing import hash_evidence

NOW = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)

BASE = {
    "issue_number": 1,
    "item_id": "PVTI_1",
    "current_status": "Todo",
    "has_ignore_label": False,
    "linked_prs": [],
    "open_spec_proposals": [],
    "last_status_actor": None,
    "last_status_at": None,
    "transition_count": 0,
}


def test_is_stable_across_dict_key_insertion_order():
    reordered = {
        "transition_count": 0,
        "issue_number": 1,
        "last_status_at": None,
        "item_id": "PVTI_1",
        "has_ignore_label": False,
        "current_status": "Todo",
        "linked_prs": [],
        "last_status_actor": None,
        "open_spec_proposals": [],
    }

    assert hash_evidence(BASE, NOW) == hash_evidence(reordered, NOW)


def test_changes_when_a_meaningful_field_changes():
    changed = {**BASE, "current_status": "In Progress"}
    assert hash_evidence(BASE, NOW) != hash_evidence(changed, NOW)


def test_is_sensitive_to_array_element_order():
    a = {**BASE, "open_spec_proposals": ["a", "b"]}
    b = {**BASE, "open_spec_proposals": ["b", "a"]}
    assert hash_evidence(a, NOW) != hash_evidence(b, NOW)


def test_unaffected_by_the_bots_own_comment_history():
    """last_status_actor/last_status_at/transition_count are all, directly
    or indirectly, driven by the bot's own prior comments - hashing them
    raw would make "unchanged evidence" never match again after the bot's
    first write (or, for transition_count, cascade into a false flapping
    flag within 3 runs even once the real PR state stopped changing).
    """
    after_bots_own_write = {
        **BASE,
        "last_status_actor": "issue-reconciler",
        "last_status_at": "2026-09-16T11:00:00+00:00",
        "transition_count": 1,
    }
    assert hash_evidence(BASE, NOW) == hash_evidence(after_bots_own_write, NOW)


def test_changes_when_a_human_override_window_expires():
    """The opposite failure mode of the above: last_status_actor/at can't
    just be dropped either, or an issue with an expired human override
    would look permanently "unchanged" and never get reprocessed.
    """
    just_inside_window = {**BASE, "last_status_actor": "alice", "last_status_at": "2026-09-15T13:00:00+00:00"}  # 23h before NOW
    just_outside_window = {**BASE, "last_status_actor": "alice", "last_status_at": "2026-09-15T11:00:00+00:00"}  # 25h before NOW
    assert hash_evidence(just_inside_window, NOW) != hash_evidence(just_outside_window, NOW)


def test_ignores_volatile_pr_fields_that_do_not_change_the_provisional_decision():
    """A push or review on an already-open, already-linked PR shouldn't by
    itself force a fresh "In progress" comment - only its identity/state
    fields matter for what decide_action would conclude.
    """
    pr = {"number": 1, "title": "x", "state": "OPEN", "merged": False, "merged_at": None, "is_draft": False, "head_ref_name": "x", "updated_at": "2026-09-01T00:00:00+00:00", "review_decision": None}
    later_activity = {**pr, "updated_at": "2026-09-16T00:00:00+00:00", "review_decision": "CHANGES_REQUESTED"}
    assert hash_evidence({**BASE, "linked_prs": [pr]}, NOW) == hash_evidence({**BASE, "linked_prs": [later_activity]}, NOW)
