"""Test table for verify.py, written before the implementation per the
Phase 1 plan. Run directly: pure, no API key, no network.
"""
from __future__ import annotations

from pr_review.pipeline import verify


class _Ctx:
    def __init__(self, convention_text="", test_index=None):
        self.convention_text = convention_text
        self.test_index = test_index or set()


def test_lint_source_is_always_confirmed_even_without_citation():
    finding = {"source": "lint", "file": "a.py", "line": 1, "citation": None}
    assert verify.precheck(finding, _Ctx()) == verify.Precheck.CONFIRMED


def test_missing_citation_is_rejected():
    finding = {"file": "a.py", "line": 1, "citation": None}
    assert verify.precheck(finding, _Ctx()) == verify.Precheck.REJECTED


def test_blank_citation_is_rejected():
    finding = {"file": "a.py", "line": 1, "citation": "   "}
    assert verify.precheck(finding, _Ctx()) == verify.Precheck.REJECTED


def test_a_genuine_lint_finding_is_confirmed_before_the_ruff_branch():
    # The only way a real ruff citation arrives: source == "lint", handled
    # by precheck's first branch.
    finding = {"file": "a.py", "line": 10, "citation": "ruff:F401", "source": "lint"}
    assert verify.precheck(finding, _Ctx()) == verify.Precheck.CONFIRMED


def test_a_model_claiming_a_ruff_citation_is_rejected():
    # No source == "lint", so Layer 1 never produced this code here: either
    # misapplied or invented. The finding survives with citation stripped;
    # the real lint finding, if any, is still in the list with its own.
    finding = {"file": "a.py", "line": 10, "citation": "ruff:F401"}
    assert verify.precheck(finding, _Ctx()) == verify.Precheck.REJECTED


def test_quoted_citation_confirmed_when_text_is_real():
    finding = {"file": "a.py", "line": 1, "citation": 'CLAUDE.md: "needs a test that asserts it directly"'}
    ctx = _Ctx(convention_text="Security-sensitive behaviour needs a test that asserts it directly, not incidentally.")
    assert verify.precheck(finding, ctx) == verify.Precheck.CONFIRMED


def test_quoted_citation_rejected_when_text_is_invented():
    finding = {"file": "a.py", "line": 1, "citation": 'CLAUDE.md: "this text does not exist anywhere"'}
    ctx = _Ctx(convention_text="Security-sensitive behaviour needs a test that asserts it directly.")
    assert verify.precheck(finding, ctx) == verify.Precheck.REJECTED


def test_quoted_citation_ignores_case_and_whitespace():
    finding = {"file": "a.py", "line": 1, "citation": 'CLAUDE.md: "NEEDS   A test"'}
    ctx = _Ctx(convention_text="needs a test that asserts it directly")
    assert verify.precheck(finding, ctx) == verify.Precheck.CONFIRMED


def test_test_name_citation_confirmed_when_test_exists():
    finding = {"file": "a.py", "line": 1, "citation": "fails test_signin_rejects_bad_password"}
    ctx = _Ctx(test_index={"test_signin_rejects_bad_password"})
    assert verify.precheck(finding, ctx) == verify.Precheck.CONFIRMED


def test_test_name_citation_rejected_when_test_does_not_exist():
    finding = {"file": "a.py", "line": 1, "citation": "fails test_does_not_exist_anywhere"}
    ctx = _Ctx(test_index={"test_signin_rejects_bad_password"})
    assert verify.precheck(finding, ctx) == verify.Precheck.REJECTED


def test_freeform_citation_needs_model():
    finding = {"file": "a.py", "line": 1, "citation": "this looks wrong to me, seems unsafe"}
    assert verify.precheck(finding, _Ctx()) == verify.Precheck.NEEDS_MODEL


def test_extract_quoted_prefers_double_quotes():
    assert verify.extract_quoted('CLAUDE.md: "the real quote"') == "the real quote"


def test_extract_quoted_falls_back_to_single_quotes():
    assert verify.extract_quoted("openspec/config.yaml: 'the real quote'") == "the real quote"


def test_extract_quoted_none_when_no_quotes():
    assert verify.extract_quoted("no quotes here") is None


def test_extract_test_name_finds_bare_name():
    assert verify.extract_test_name("see test_signin_rejects_bad_password for proof") == "test_signin_rejects_bad_password"


def test_extract_test_name_none_when_absent():
    assert verify.extract_test_name("no test reference here") is None


def test_normalize_collapses_whitespace_and_case():
    assert verify.normalize("  Needs\n  A   Test  ") == "needs a test"


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"ok ({len(TESTS)} tests)")
