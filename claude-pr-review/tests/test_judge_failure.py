"""Layer 2 must fail closed, like Layer 3 already did.

Before this, judge.py called agent.run() bare: one transient 500, one
refusal, or one oversized diff hitting max_tokens took down the whole run.
No verdict, no comment, just a red X and a traceback in the CI log for an
author with no idea what happened - on exactly the large PRs that most need
reviewing.

No API key, no network: the agent call is stubbed.
"""
from __future__ import annotations

import anthropic
from pr_review.core import agent
from pr_review.pipeline import gate, judge


def _patched_judge(run_impl, lint_findings=None):
    """Run judge() with the model call and Layer 1 both stubbed."""
    originals = (judge.agent.run, judge.lint.run, judge.target.changed_python_files,
                 judge.target.get_diff, judge.target.repo_rules, agent.time.sleep)
    judge.agent.run = run_impl
    judge.lint.run = lambda files: {"status": "fail", "findings": lint_findings or []}
    judge.target.changed_python_files = lambda t: []
    judge.target.get_diff = lambda t: "diff"
    judge.target.repo_rules = lambda: {}
    agent.time.sleep = lambda *_: None
    try:
        return judge.judge(object(), "1")
    finally:
        (judge.agent.run, judge.lint.run, judge.target.changed_python_files,
         judge.target.get_diff, judge.target.repo_rules, agent.time.sleep) = originals


_LINT = [{"file": "a.py", "line": 1, "code": "S105", "message": "hardcoded password"}]


def test_a_failing_layer_2_does_not_raise():
    def always_fails(*a, **k):
        raise agent.AgentError("Hit max_tokens before producing a final answer")

    result = _patched_judge(always_fails)
    assert "layer2_error" in result


def test_lint_findings_still_ship_when_layer_2_dies():
    # Layer 1 runs before the model call and is ground truth - a lint-only
    # review is worth more than no review at all.
    def always_fails(*a, **k):
        raise agent.AgentError("boom")

    result = _patched_judge(always_fails, lint_findings=_LINT)
    assert len(result["findings"]) == 1
    assert result["findings"][0]["citation"] == "ruff:S105"


def test_a_failed_layer_2_never_reports_ready():
    # The point of failing closed: a green verdict from a review that never
    # ran is indistinguishable from a genuinely clean one.
    def always_fails(*a, **k):
        raise agent.AgentError("boom")

    result = _patched_judge(always_fails)          # no lint findings either
    report, ready = gate.render({"findings": result["findings"],
                                 "layer2_error": result["layer2_error"]})
    assert ready is False
    assert "Review incomplete" in report
    assert "Ready to merge: no" in report


def test_a_clean_run_with_no_error_is_still_allowed_to_be_ready():
    def succeeds(*a, **k):
        return {"findings": []}

    result = _patched_judge(succeeds)
    assert "layer2_error" not in result
    report, ready = gate.render({"findings": result["findings"]})
    assert ready is True


def test_retryable_errors_are_retried():
    calls = []

    def fails_then_succeeds(*a, **k):
        calls.append(1)
        if len(calls) < 3:
            raise agent.AgentError("transient")
        return {"findings": []}

    result = _patched_judge(fails_then_succeeds)
    assert len(calls) == 3
    assert "layer2_error" not in result


def test_non_retryable_errors_are_not_retried():
    # A 400 fails identically every time; retrying just burns the backoff.
    calls = []

    def bad_request(*a, **k):
        calls.append(1)
        raise anthropic.BadRequestError(
            "bad request", response=_DummyResponse(), body=None
        )

    result = _patched_judge(bad_request)
    assert len(calls) == 1
    assert "layer2_error" in result


class _DummyResponse:
    status_code = 400
    headers: dict = {}
    request = None


def test_max_tokens_is_high_enough_for_a_large_finding_set():
    # The crash that started this: a 36-file diff produced more findings
    # JSON than an 8000-token response could hold.
    assert agent.MAX_TOKENS >= 16_000
    assert agent.MAX_TOKENS_STREAMING >= 64_000


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"ok ({len(TESTS)} tests)")
