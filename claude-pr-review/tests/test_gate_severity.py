"""Self-check for gate.py: severity-gated blocking (a cited MINOR is a
non-blocking nit, only CRITICAL/MAJOR block), the three-section verdict
(1.6) - an uncited/rejected CRITICAL or MAJOR, and any unverified finding,
render under "worth a look" rather than being buried in the nits section -
and the invariant-4 severity floor (2.1): a finding whose final severity
ranks below what verify.py recorded as Layer 2's own severity is a hard
failure, never a silent pass-through.
"""
from __future__ import annotations

from pr_review.pipeline import gate


def _finding(severity, citation="some-requirement", unverified=False):
    f = {"file": "a.py", "line": 1, "severity": severity, "summary": "x", "citation": citation}
    if unverified:
        f["unverified"] = True
    return f


def test_cited_minor_does_not_block_and_is_a_nit():
    report, ready = gate.render({"findings": [_finding("MINOR")]})
    assert ready is True
    assert "Ready to merge: yes" in report
    assert "## Nits" in report
    assert "## Blocking" not in report
    assert "worth a look" not in report


def test_cited_major_and_critical_block():
    for severity in ("MAJOR", "CRITICAL"):
        report, ready = gate.render({"findings": [_finding(severity)]})
        assert ready is False
        assert "Ready to merge: no" in report
        assert "## Blocking" in report


def test_uncited_unverified_critical_does_not_block_but_is_worth_a_look():
    # Layer 3 never confirmed it, so there is no evidence to block on.
    report, ready = gate.render({"findings": [_finding("CRITICAL", citation=None)]})
    assert ready is True
    assert "## Blocking" not in report
    assert "## Unblocked but worth a look" in report
    assert "## Nits" not in report


def test_uncited_critical_blocks_once_layer_3_verified_it():
    # MD5-for-signing is broken whether or not CLAUDE.md says so. The
    # verification is the evidence; a citation would only be paperwork.
    f = _finding("CRITICAL", citation=None)
    f["verified"] = True
    report, ready = gate.render({"findings": [f]})
    assert ready is False
    assert "## Blocking" in report
    assert "no citation — verified by Layer 3" in report
    assert "cites: None" not in report


def test_uncited_verified_major_still_does_not_block():
    # At MAJOR, "is this worth blocking on" is a local judgement this repo
    # gets to make, so a citation stays the right gate.
    f = _finding("MAJOR", citation=None)
    f["verified"] = True
    _, ready = gate.render({"findings": [f]})
    assert ready is True


def test_a_lint_passthrough_cannot_block_uncited():
    # `verified` is set only by verify._apply_verification(), so a finding
    # Layer 3 never looked at can never qualify on this path.
    f = _finding("CRITICAL", citation=None)
    f["source"] = "lint"
    _, ready = gate.render({"findings": [f]})
    assert ready is True


def test_unverified_finding_is_worth_a_look_even_when_minor():
    report, ready = gate.render({"findings": [_finding("MINOR", unverified=True)]})
    assert ready is True
    assert "## Unblocked but worth a look" in report
    assert "[unverified]" in report


def test_unverified_footer_counts_unverified_findings():
    report, _ = gate.render({"findings": [_finding("MAJOR", citation=None, unverified=True)]})
    assert "Verification unavailable for 1 finding(s)" in report


def test_suppressed_count_footer():
    report, _ = gate.render({"findings": [], "suppressed_count": 4})
    assert "4 additional finding(s) suppressed" in report


def test_severity_floor_holds_when_absent_defaults_to_own_severity():
    # A finding with no l2_severity key at all (e.g. built directly in a
    # test, not through verify.py) has nothing to have been downgraded
    # from, so it is left exactly as it is.
    report, ready = gate.render({"findings": [_finding("MAJOR")]})
    assert ready is False


def test_severity_floor_allows_escalation():
    f = _finding("CRITICAL")
    f["l2_severity"] = "MAJOR"
    report, ready = gate.render({"findings": [f]})
    assert ready is False


def test_severity_floor_repairs_a_downgrade_upward():
    # Raising here would kill the run before post.py writes anything, so
    # the one review that caught a downgrade would be the one nobody sees.
    # The finding is restored to Layer 2's severity and blocks accordingly.
    f = _finding("MINOR")
    f["l2_severity"] = "CRITICAL"
    report, ready = gate.render({"findings": [f]})
    assert ready is False
    assert "## Blocking" in report
    assert "CRITICAL" in report
    assert "restored" in report


def test_severity_floor_repair_does_not_mutate_the_caller_s_finding():
    f = _finding("MINOR")
    f["l2_severity"] = "CRITICAL"
    gate.render({"findings": [f]})
    assert f["severity"] == "MINOR"


def test_nit_with_fingerprint_renders_as_dismissable_checkbox():
    f = _finding("MINOR")
    f["fp"] = "a1b2c3d4e5f6a1b2"
    report, _ = gate.render({"findings": [f]})
    assert "- [ ] `a1b2c3d4`" in report
    assert "Tick a box to dismiss" in report


def test_nit_without_fingerprint_renders_as_plain_bullet():
    report, _ = gate.render({"findings": [_finding("MINOR")]})
    assert "- [ ]" not in report
    assert "Tick a box to dismiss" not in report


def test_dismissed_finding_is_excluded_from_blocking_and_shown_collapsed():
    f = _finding("CRITICAL")
    f["fp"] = "a1b2c3d4e5f6a1b2"
    f["status"] = "dismissed"
    report, ready = gate.render({"findings": [f]})
    assert ready is True  # dismissed, even a CRITICAL, never blocks
    assert "## Blocking" not in report
    assert "Previously dismissed (1)" in report
    assert "- [x] `a1b2c3d4`" in report


def test_resolved_finding_is_excluded_and_shown_collapsed():
    f = _finding("MAJOR")
    f["fp"] = "a1b2c3d4e5f6a1b2"
    f["status"] = "resolved"
    report, ready = gate.render({"findings": [f]})
    assert ready is True
    assert "## Blocking" not in report
    assert "Resolved (1)" in report
    assert "code no longer found" in report


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"ok ({len(TESTS)} tests)")
