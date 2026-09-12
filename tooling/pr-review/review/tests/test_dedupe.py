"""Tests for review.dedupe, written from the pr-review spec's "Suppress duplicate
findings" requirement: the same underlying issue found by more than one source
results in one comment; genuinely different concerns do not get merged away.

Includes a documented known limitation (see design.md's "Risks" entry on this
heuristic): fuzzy title matching is character-based, so two very differently worded
descriptions of the same real-world issue may not be recognised as duplicates. That
is asserted here as current behaviour, not silently assumed.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from review.dedupe import collapse_duplicates, find_match  # noqa: E402
from review.schema import Finding  # noqa: E402


def _finding(**overrides):
    base = dict(
        category="security",
        severity="major",
        file="settings.py",
        line=10,
        title="Hardcoded secret in settings.py",
        explanation="explanation",
        source="security-review",
    )
    base.update(overrides)
    return Finding(**base)


def test_near_identical_titles_at_the_same_location_collapse_to_one():
    a = _finding(title="Hardcoded secret in settings.py", source="security-review")
    b = _finding(title="Hardcoded secret found in settings.py", source="code-quality", severity="minor")
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 1


def test_duplicate_keeps_the_higher_severity_finding_and_notes_the_other_source():
    a = _finding(severity="minor", source="code-quality")
    b = _finding(severity="blocker", source="security-review")
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 1
    assert survivors[0].severity == "blocker"
    assert "code-quality" in survivors[0].explanation


def test_distinct_titles_at_the_same_location_are_not_merged():
    a = _finding(title="Hardcoded secret in settings.py")
    b = _finding(
        title="Function exceeds 200 lines and should be split",
        category="code-quality",
        source="code-quality",
    )
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 2


def test_same_title_at_a_different_file_is_not_merged():
    a = _finding(title="Hardcoded secret", file="settings.py")
    b = _finding(title="Hardcoded secret", file="other.py")
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 2


def test_same_title_far_apart_on_the_same_file_is_not_merged():
    a = _finding(title="Missing error handling", line=10)
    b = _finding(title="Missing error handling", line=200)
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 2


def test_known_limitation_very_differently_worded_duplicates_are_not_caught():
    """Same underlying issue, described in unrelated wording - the character-based
    fuzzy match does not catch this. Documented in design.md as a risk requiring
    tuning against real examples before this is trusted in production.
    """
    a = _finding(title="Hardcoded secret in settings.py")
    b = _finding(title="SECRET_KEY should not be committed to source", category="code-quality", source="code-quality")
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 2


def test_real_reworded_pair_from_pr11_is_recognised_as_duplicate():
    """Real titles from two independent architecture-review subagent runs on the same
    unchanged code (PR #11, ibtisam-saeed/ai-on-boarding) describing the same raw-SQL
    finding. Similarity is 0.568 - below the old 0.6 threshold, which is why this pair
    was reposted instead of recognised as already-handled. See traceability.md.
    """
    a = _finding(
        title="Raw SQL cursor bypasses the ORM layer this project standardises on",
        category="architecture",
        source="architecture-review",
        line=25,
    )
    b = _finding(
        title="Hand-written SQL data access bypasses the ORM pattern used throughout this project",
        category="architecture",
        source="architecture-review",
        line=25,
    )
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 1
    assert find_match(b, [a]) is not None


def test_real_third_rewording_from_pr11_is_recognised_via_category_not_title():
    """A third independent architecture-review run on the same unchanged PR #11
    code produced a third wording of the raw-SQL finding. Its title similarity
    against the *second* run's wording is 0.386 - well below any threshold that
    still keeps the "distinct titles" and "known limitation" fixtures unmatched -
    proving title similarity alone cannot converge across repeated independent
    rewordings. `find_match` must instead catch this via same location + same
    category (`review/dedupe.py`'s deliberate design for this specific check).
    """
    posted = _finding(
        title="Hand-written SQL data access bypasses the ORM pattern used throughout this project",
        category="architecture",
        source="architecture-review",
        line=25,
    )
    candidate = _finding(
        title="Raw SQL cursor reimplements ORM query and bypasses the project's data-access pattern",
        category="architecture",
        source="architecture-review",
        line=25,
    )
    assert find_match(candidate, [posted]) is not None


def test_find_match_still_respects_category_for_cross_category_low_similarity():
    """The category-based path must not become a blanket "same location matches
    anything" rule: a genuinely different category at the same location, with low
    title similarity, must still be treated as a distinct, not-yet-posted finding -
    the same cross-category limitation `test_known_limitation_...` documents for
    `collapse_duplicates` applies here too, deliberately unchanged.
    """
    posted = _finding(title="Hardcoded secret in settings.py", category="security")
    candidate = _finding(
        title="SECRET_KEY should not be committed to source",
        category="code-quality",
        source="code-quality",
    )
    assert find_match(candidate, [posted]) is None


def test_real_rescoped_pair_from_pr11_is_recognised_as_duplicate():
    """Same real run: the second architecture-review call consolidated two of the
    first run's separate findings (a placement concern and a duplicated-fixture
    concern) into one reworded finding at the same location. Similarity is 0.610 -
    just over the old 0.6 threshold, yet this was still reposted in production
    (see traceability.md), so the threshold needed real margin, not just a pass.
    """
    a = _finding(
        title="Debug scratch module added to the application package with no backing spec or change",
        category="architecture",
        source="architecture-review",
        line=1,
    )
    b = _finding(
        title="Review-tooling scratch fixture added to the Django application package, "
        "duplicating an existing fixture",
        category="architecture",
        source="architecture-review",
        line=1,
    )
    survivors = collapse_duplicates([a, b])
    assert len(survivors) == 1
    assert find_match(b, [a]) is not None
