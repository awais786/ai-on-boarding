"""Tests for judge.py's 1.3 (findings cap) and 1.4 (merge, not drop). No API
key, no network - these exercise the pure list-shuffling logic only.
"""
from __future__ import annotations

from pr_review.pipeline import judge


def _lint_finding(file="a.py", line=10, severity="MINOR", summary="lint msg"):
    return {"file": file, "line": line, "severity": severity, "summary": summary, "citation": "ruff:F401", "source": "lint"}


def _model_finding(file="a.py", line=10, severity="MAJOR", summary="model msg", citation="c"):
    return {"file": file, "line": line, "severity": severity, "summary": summary, "citation": citation}


def test_merge_overlapping_finding_keeps_both_summaries_and_max_severity():
    lint_findings = [_lint_finding(severity="MINOR", summary="unused import")]
    model_findings = [_model_finding(line=11, severity="MAJOR", summary="actually a real bug here")]
    merged = judge.merge_lint_and_model(lint_findings, model_findings)
    assert len(merged) == 1
    assert merged[0]["severity"] == "MAJOR"
    assert merged[0]["source"] == "lint"  # still the lint-origin finding, just enriched
    # Both survive: the citation attests to the linter's message, so that
    # leads, with the model's observation appended.
    assert "unused import" in merged[0]["summary"]
    assert "actually a real bug here" in merged[0]["summary"]


def test_merge_never_loses_what_the_citation_attests():
    # Regression for a live-run defect: a CRITICAL citing ruff:S105
    # (hardcoded password) shipped with a summary about a missing test, so
    # the verdict never mentioned the credential the citation was about.
    lint_findings = [_lint_finding(severity="CRITICAL", summary="Possible hardcoded password assigned to: SECRET")]
    model_findings = [_model_finding(line=11, severity="MAJOR", summary="no test covers this module")]
    [merged] = judge.merge_lint_and_model(lint_findings, model_findings)
    assert "hardcoded password" in merged["summary"]
    assert merged["severity"] == "CRITICAL"


def test_merge_does_not_duplicate_an_identical_summary():
    lint_findings = [_lint_finding(summary="same text")]
    model_findings = [_model_finding(line=11, summary="same text")]
    [merged] = judge.merge_lint_and_model(lint_findings, model_findings)
    assert merged["summary"] == "same text"


def test_merge_near_miss_within_window_still_merges():
    lint_findings = [_lint_finding(line=10)]
    model_findings = [_model_finding(line=13)]  # 3 lines away, at the window edge
    merged = judge.merge_lint_and_model(lint_findings, model_findings)
    assert len(merged) == 1


def test_merge_outside_window_appends_standalone():
    lint_findings = [_lint_finding(line=10)]
    model_findings = [_model_finding(line=14)]  # 4 lines away, outside the window
    merged = judge.merge_lint_and_model(lint_findings, model_findings)
    assert len(merged) == 2


def test_merge_different_file_never_merges():
    lint_findings = [_lint_finding(file="a.py", line=10)]
    model_findings = [_model_finding(file="b.py", line=10)]
    merged = judge.merge_lint_and_model(lint_findings, model_findings)
    assert len(merged) == 2


def test_merge_no_overlap_keeps_all():
    lint_findings = [_lint_finding(line=10)]
    model_findings = [_model_finding(file="c.py", line=99)]
    merged = judge.merge_lint_and_model(lint_findings, model_findings)
    assert len(merged) == 2


def test_cap_truncates_to_limit():
    findings = [_model_finding(line=i) for i in range(20)]
    kept, suppressed = judge._cap_findings(findings, limit=15)
    assert len(kept) == 15
    assert suppressed == 5


def test_cap_keeps_highest_severity_first():
    findings = [
        _model_finding(line=1, severity="MINOR", citation="x"),
        _model_finding(line=2, severity="CRITICAL", citation="x"),
        _model_finding(line=3, severity="MAJOR", citation="x"),
    ]
    kept, suppressed = judge._cap_findings(findings, limit=2)
    assert suppressed == 1
    assert [f["severity"] for f in kept] == ["CRITICAL", "MAJOR"]


def test_cap_prefers_cited_within_same_severity():
    findings = [
        _model_finding(line=1, severity="MAJOR", citation=None),
        _model_finding(line=2, severity="MAJOR", citation="real citation"),
    ]
    kept, suppressed = judge._cap_findings(findings, limit=1)
    assert kept[0]["citation"] == "real citation"


def test_cap_under_limit_suppresses_nothing():
    findings = [_model_finding(line=1)]
    kept, suppressed = judge._cap_findings(findings, limit=15)
    assert len(kept) == 1
    assert suppressed == 0


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"ok ({len(TESTS)} tests)")
