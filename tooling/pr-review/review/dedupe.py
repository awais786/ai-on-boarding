"""Collapses findings that describe the same underlying issue - both within a single
batch of new candidates (`collapse_duplicates`) and against what a pull request
already carries (`find_match`, used by publish.py's already-posted check). Both
share the same location heuristic (same file, line within `LINE_WINDOW`), but use
different signals for "is this the same issue": `collapse_duplicates` requires
title similarity, since it dedupes findings generated together in one run, where
two genuinely distinct concerns at nearby lines are a real case to preserve.
`find_match` additionally treats a shared category as sufficient on its own,
because repeated independent LLM calls reviewing unchanged code do not just fail
to reproduce a title byte-for-byte - they can drift far enough, round over round,
that no fixed title-similarity threshold reliably catches every pair. See
openspec/changes/add-pr-review-agent/traceability.md for the real runs that proved
this (title similarity across three independent rewordings of the same finding:
0.568, 0.386, 0.507 - never consistently above any one cutoff).

See openspec/changes/add-pr-review-agent/design.md - Decision 5 and the "Risks" entry
on this heuristic needing validation against real examples before it is trusted.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from review.schema import SEVERITY_RANK, Finding

# Widened from 3 after a fourth real re-trigger (PR #11) anchored the same raw-SQL finding to
# line 20 (the `def get_user_orders(user_id):` line) instead of line 25 (the `cursor.execute(...)`
# line inside it) that all three prior runs had used - a 5-line drift for the identical
# underlying, function-level issue, which the old window rejected before category matching in
# find_match ever ran. Unlike title wording, a function's span in an unchanged file doesn't grow
# between runs, so this drift is bounded, not open-ended - 8 gives real margin over the observed
# 5-line spread for a typical small function. See traceability.md.
LINE_WINDOW = 8
# Lowered from 0.6 after two real reworded/re-scoped duplicates from an independent subagent
# re-run (PR #11 on ibtisam-saeed/ai-on-boarding) scored 0.568 and 0.610 against their originals
# and were reposted instead of recognised as already-handled - see traceability.md. 0.5 leaves
# clear margin below both the "distinct titles" (0.208) and "very differently worded duplicate"
# (0.320) cases already covered by test_dedupe.py, while catching both real pairs.
TITLE_SIMILARITY_THRESHOLD = 0.5


def _title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def _same_location(a: Finding, b: Finding) -> bool:
    if a.file != b.file:
        return False
    if a.line is None or b.line is None:
        return a.line == b.line
    return abs(a.line - b.line) <= LINE_WINDOW


def find_match(candidate: Finding, pool: list[Finding]) -> Finding | None:
    """The first finding in `pool` that appears to describe the same underlying
    issue as `candidate` (same location, and either a similar title or the same
    category), or None. Used against already-posted findings reconstructed from a
    pull request's existing comments - unlike `collapse_duplicates`, there is no
    "survivor" to pick here, since an already-posted finding always wins: the
    candidate is simply not reposted.

    Matching on category (not title similarity alone) once location matches is
    deliberate: three independent real re-triggers on the same unchanged code (PR
    #11 on ibtisam-saeed/ai-on-boarding) produced three different rewordings of the
    same finding whose pairwise title similarity - 0.568, 0.386, 0.507 - never
    reliably cleared any single fixed threshold, each round drifting a different
    amount from each prior wording. No fixed character-similarity cutoff converges
    against unbounded independent rewording, so for this specific check (has this
    skill already told us about this location before?) same-location-and-category
    is treated as sufficient on its own. Title similarity is kept as an additional,
    looser path so a same-titled finding from a *different* category can still be
    caught (the cross-category case remains a documented limitation - see
    test_dedupe.py). This is deliberately not applied to collapse_duplicates, which
    dedupes findings *within* one run: two distinct concerns from the same skill at
    nearby lines in a single call are a real, if uncommon, case that should not be
    silently merged just because they share a category - see traceability.md.
    """
    for other in pool:
        if _same_location(candidate, other) and (
            candidate.category == other.category
            or _title_similarity(candidate.title, other.title) >= TITLE_SIMILARITY_THRESHOLD
        ):
            return other
    return None


def _pick_survivor(a: Finding, b: Finding) -> tuple[Finding, Finding]:
    """Returns (survivor, dropped), keeping the higher-severity finding."""
    if SEVERITY_RANK[b.severity] > SEVERITY_RANK[a.severity]:
        return b, a
    return a, b


def _note_also_flagged(finding: Finding, other_sources: list[str]) -> Finding:
    if not other_sources:
        return finding
    sources = ", ".join(sorted(set(other_sources)))
    return finding.model_copy(
        update={"explanation": f"{finding.explanation}\n\n(Also flagged by: {sources}.)"}
    )


def collapse_duplicates(findings: list[Finding]) -> list[Finding]:
    """Merges findings at the same location whose titles are near-identical, keeping
    the higher-severity one and noting which other sources agreed. Findings at the
    same location with genuinely different titles are left as separate findings -
    that is multiple sources raising distinct concerns, not a duplicate.
    """
    survivors: list[Finding] = []
    merged_sources: list[list[str]] = []

    for finding in findings:
        matched_index = None
        for index, survivor in enumerate(survivors):
            if _same_location(finding, survivor) and (
                _title_similarity(finding.title, survivor.title) >= TITLE_SIMILARITY_THRESHOLD
            ):
                matched_index = index
                break

        if matched_index is None:
            survivors.append(finding)
            merged_sources.append([])
            continue

        current, dropped = survivors[matched_index], finding
        winner, loser = _pick_survivor(current, dropped)
        merged_sources[matched_index].append(loser.source)
        survivors[matched_index] = winner

    return [
        _note_also_flagged(survivor, sources)
        for survivor, sources in zip(survivors, merged_sources)
    ]
