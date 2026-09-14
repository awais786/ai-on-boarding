from __future__ import annotations

from issue_reconciler.hashing import hash_evidence

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

    assert hash_evidence(BASE) == hash_evidence(reordered)


def test_changes_when_a_meaningful_field_changes():
    changed = {**BASE, "current_status": "In Progress"}
    assert hash_evidence(BASE) != hash_evidence(changed)


def test_is_sensitive_to_array_element_order():
    a = {**BASE, "open_spec_proposals": ["a", "b"]}
    b = {**BASE, "open_spec_proposals": ["b", "a"]}
    assert hash_evidence(a) != hash_evidence(b)
