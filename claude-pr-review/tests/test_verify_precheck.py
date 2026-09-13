"""Tests for verify.py's 1.2 (citation precheck integration) and 1.5
(verifier fails closed). No API key, no network - the model client is
stubbed or never reached for the CONFIRMED/REJECTED paths.

Every finding verify.verify() returns now carries `l2_severity` (Phase 2's
severity-floor bookkeeping - see gate.py's _assert_severity_floor), so
these compare individual fields rather than the whole dict where that
extra key would otherwise make an equality check fail for the wrong reason.
"""
from __future__ import annotations

from pr_review.core import agent
from pr_review.lib import severity
from pr_review.pipeline import verify


class _UnreachableClient:
    def __getattr__(self, name):
        raise AssertionError(f"client.{name} must not be reached for a deterministic precheck outcome")


def _finding(file="a.py", line=1, severity="MAJOR", citation="x", summary="s"):
    return {"file": file, "line": line, "severity": severity, "citation": citation, "summary": summary}


def test_confirmed_citation_skips_model_and_keeps_finding_unchanged():
    finding = _finding(citation='CLAUDE.md: "needs a test that asserts it directly"')
    rules = {"CLAUDE.md": "Security-sensitive behaviour needs a test that asserts it directly, not incidentally."}
    result = verify.verify(_UnreachableClient(), diff="", rules=rules, findings={"findings": [finding]})
    [out] = result["findings"]
    assert out["citation"] == finding["citation"]
    assert out["severity"] == finding["severity"]
    assert out["l2_severity"] == finding["severity"]


def test_rejected_citation_skips_model_and_strips_citation_only():
    # MINOR, because a rejected citation at CRITICAL/MAJOR now routes to
    # Layer 3 - see test_a_critical_whose_citation_is_rejected_is_still_verified.
    finding = _finding(severity="MINOR", citation='CLAUDE.md: "this text is invented and does not exist"')
    rules = {"CLAUDE.md": "Something else entirely."}
    result = verify.verify(_UnreachableClient(), diff="", rules=rules, findings={"findings": [finding]})
    [out] = result["findings"]
    assert out["citation"] is None
    assert out["severity"] == "MINOR"  # severity is never touched by a rejected citation


def test_missing_citation_skips_model_and_stays_uncited():
    # MINOR: at CRITICAL/MAJOR an uncited finding now routes to Layer 3 so
    # `escalate_to` can fire. A MINOR can never block, so it isn't worth a call.
    finding = _finding(severity="MINOR", citation=None)
    result = verify.verify(_UnreachableClient(), diff="", rules={}, findings={"findings": [finding]})
    [out] = result["findings"]
    assert out["citation"] is None


def test_needs_model_citation_calls_the_agent_without_severity():
    finding = _finding(citation="this looks wrong to me, no quote or test name")
    calls = []

    def fake_run(client, model, system, stable_content, variable_content="", **kwargs):
        calls.append(variable_content)
        return {"verified": True, "citation_holds": True, "escalate_to": None, "reasoning": "checked it"}

    original = agent.run
    verify.agent.run = fake_run
    try:
        result = verify.verify(object(), diff="d", rules={}, findings={"findings": [finding]})
    finally:
        verify.agent.run = original

    assert len(calls) == 1
    assert '"severity"' not in calls[0]  # 2.2: the verifier is never shown Layer 2's severity
    assert result["findings"][0]["citation"] == finding["citation"]


def test_verified_false_drops_the_finding():
    finding = _finding()

    def fake_run(client, model, system, stable_content, variable_content="", **kwargs):
        return {"verified": False, "citation_holds": False, "escalate_to": None, "reasoning": "doesn't hold up"}

    original = agent.run
    verify.agent.run = fake_run
    try:
        result = verify.verify(object(), diff="d", rules={}, findings={"findings": [finding]})
    finally:
        verify.agent.run = original

    assert result["findings"] == []


def test_escalate_to_raises_severity_but_never_lowers():
    finding = _finding(severity="MAJOR")

    def fake_run(client, model, system, stable_content, variable_content="", **kwargs):
        return {"verified": True, "citation_holds": True, "escalate_to": "CRITICAL", "reasoning": "worse than it looked"}

    original = agent.run
    verify.agent.run = fake_run
    try:
        result = verify.verify(object(), diff="d", rules={}, findings={"findings": [finding]})
    finally:
        verify.agent.run = original

    [out] = result["findings"]
    assert out["severity"] == "CRITICAL"
    assert out["l2_severity"] == "MAJOR"  # the floor gate.py checks against


def test_fails_closed_after_retries_preserves_severity_and_citation():
    finding = _finding(severity="CRITICAL", citation="this looks wrong to me, no quote or test name")

    def always_fails(client, model, system, stable_content, variable_content="", **kwargs):
        raise agent.AgentError("simulated transient failure")

    original_run, original_sleep = agent.run, agent.time.sleep
    verify.agent.run = always_fails
    agent.time.sleep = lambda *_: None  # don't actually wait through the backoff in tests
    try:
        result = verify.verify(object(), diff="d", rules={}, findings={"findings": [finding]})
    finally:
        verify.agent.run = original_run
        agent.time.sleep = original_sleep

    [out] = result["findings"]
    assert out["unverified"] is True
    assert out["severity"] == "CRITICAL"           # never downgraded
    assert out["citation"] == finding["citation"]  # never stripped by an infra failure


def test_an_uncited_critical_is_verified_and_can_then_block():
    # Before this it was stripped with no model call, so a real defect no
    # written convention happens to cover could never block - which meant
    # the reviewer could only ever block on process rules.
    calls = []

    def fake_run(client, model, system, stable_content, variable_content="", **kwargs):
        calls.append(model)
        return {"verified": True, "citation_holds": False, "escalate_to": None, "reasoning": "held"}

    original = verify.agent.run
    verify.agent.run = fake_run
    try:
        result = verify.verify(
            object(), diff="d", rules={},
            findings={"findings": [_finding(severity="CRITICAL", citation=None)]},
        )
    finally:
        verify.agent.run = original

    assert calls == [verify.MODEL], "an uncited CRITICAL must reach Layer 3"
    [out] = result["findings"]
    assert out["verified"] is True
    assert severity.is_blocking(out) is True


def test_an_uncited_critical_layer_3_rejects_does_not_block():
    def fake_run(client, model, system, stable_content, variable_content="", **kwargs):
        return {"verified": False, "citation_holds": False, "escalate_to": None, "reasoning": "no"}

    original = verify.agent.run
    verify.agent.run = fake_run
    try:
        result = verify.verify(
            object(), diff="d", rules={},
            findings={"findings": [_finding(severity="CRITICAL", citation=None)]},
        )
    finally:
        verify.agent.run = original

    assert result["findings"] == []
    assert result["rejected_count"] == 1


def test_a_critical_whose_citation_is_rejected_is_still_verified():
    # Regression for a live miss: Layer 2 "cited" a prompt-injection attempt
    # by quoting the injected text, precheck correctly rejected that (it is
    # not in the trusted rules), and the CRITICAL then passed through
    # unverified and unable to block. Where a citation came from says
    # nothing about whether the defect behind it is real.
    calls = []

    def fake_run(client, model, system, stable_content, variable_content="", **kwargs):
        calls.append(model)
        return {"verified": True, "citation_holds": False, "escalate_to": None, "reasoning": "real"}

    finding = _finding(severity="CRITICAL", citation='"text that is nowhere in the rules"')
    original = verify.agent.run
    verify.agent.run = fake_run
    try:
        result = verify.verify(object(), diff="d", rules={"CLAUDE.md": "unrelated"},
                               findings={"findings": [finding]})
    finally:
        verify.agent.run = original

    assert calls == [verify.MODEL], "a CRITICAL with a rejected citation must still be verified"
    [out] = result["findings"]
    assert out["citation"] is None
    assert out["verified"] is True
    assert severity.is_blocking(out) is True


def test_a_minor_whose_citation_is_rejected_still_skips_the_model():
    finding = _finding(severity="MINOR", citation='"text that is nowhere in the rules"')
    result = verify.verify(_UnreachableClient(), diff="", rules={"CLAUDE.md": "unrelated"},
                           findings={"findings": [finding]})
    [out] = result["findings"]
    assert out["citation"] is None
    assert severity.is_blocking(out) is False


def test_an_uncited_major_reaches_the_model_so_it_can_be_escalated():
    # Layer 2 under-rates security findings: a live run called two
    # disagreeing password policies on the same User model a MAJOR. Uncited,
    # it used to be dropped here without ever reaching `escalate_to`, the
    # one mechanism designed to promote exactly that.
    def escalates(client, model, system, stable_content, variable_content="", **kwargs):
        return {"verified": True, "citation_holds": False,
                "escalate_to": "CRITICAL", "reasoning": "weakens an auth path"}

    original = verify.agent.run
    verify.agent.run = escalates
    try:
        result = verify.verify(object(), diff="d", rules={},
                               findings={"findings": [_finding(severity="MAJOR", citation=None)]})
    finally:
        verify.agent.run = original

    [out] = result["findings"]
    assert out["severity"] == "CRITICAL"
    assert out["l2_severity"] == "MAJOR"
    assert severity.is_blocking(out) is True


def test_an_uncited_major_that_is_not_escalated_still_does_not_block():
    # The bar is unchanged: only a CRITICAL blocks without a citation.
    def no_escalation(client, model, system, stable_content, variable_content="", **kwargs):
        return {"verified": True, "citation_holds": False,
                "escalate_to": None, "reasoning": "real but not critical"}

    original = verify.agent.run
    verify.agent.run = no_escalation
    try:
        result = verify.verify(object(), diff="d", rules={},
                               findings={"findings": [_finding(severity="MAJOR", citation=None)]})
    finally:
        verify.agent.run = original

    [out] = result["findings"]
    assert out["severity"] == "MAJOR"
    assert severity.is_blocking(out) is False


def test_an_uncited_minor_never_reaches_the_model():
    # Keeps call volume bounded - a MINOR can never block however it's rated.
    result = verify.verify(
        _UnreachableClient(), diff="", rules={},
        findings={"findings": [_finding(severity="MINOR", citation=None)]},
    )
    [out] = result["findings"]
    assert out["citation"] is None
    assert out.get("verified") is not True
    assert severity.is_blocking(out) is False


def test_every_severity_is_verified_by_the_strong_model():
    # Layer 3 is the gate, so it does not get a cheap model at any severity.
    # A live run with Haiku verifying rejected 4 of 5 model findings,
    # including a genuine cross-file password-policy regression.
    models_used = []

    def fake_run(client, model, system, stable_content, variable_content="", **kwargs):
        models_used.append(model)
        return {"verified": True, "citation_holds": True, "escalate_to": None, "reasoning": "ok"}

    findings = {
        "findings": [
            _finding(file="a.py", severity="CRITICAL", citation="freeform, no quote or test name here"),
            _finding(file="b.py", severity="MAJOR", citation="freeform, no quote or test name here either"),
        ]
    }
    original = agent.run
    verify.agent.run = fake_run
    try:
        verify.verify(object(), diff="d", rules={}, findings=findings)
    finally:
        verify.agent.run = original

    assert models_used == [verify.MODEL, verify.MODEL]
    assert "haiku" not in verify.MODEL


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"ok ({len(TESTS)} tests)")
