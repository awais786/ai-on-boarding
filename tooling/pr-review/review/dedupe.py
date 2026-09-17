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
that no fixed title-similarity threshold reliably catches every pair.

See openspec/changes/add-pr-review-agent/design.md - Decision 5 and the "Risks" entry,
and openspec/changes/add-pr-review-agent/traceability.md for the real-world evidence
behind this module's current calibration.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from review.schema import SEVERITY_RANK, Finding

# A function-level finding can legitimately be anchored to different lines within the same
# function across independent runs (e.g. the `def` line vs. a call inside it). Unlike title
# wording, this drift is bounded - a function's span in an unchanged file can't grow between
# runs - so a window wide enough to cover a typical small function is safe. See traceability.md
# for the real-world drift that calibrated this value.
LINE_WINDOW = 8
# How similar two titles must be, at the same location, to be treated as the same finding.
# Calibrated against both real near-duplicate and real distinct-concern examples - see
# test_dedupe.py's fixtures and traceability.md for the evidence behind this value.
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
    deliberate: independent LLM calls reviewing unchanged code can reword or
    re-scope the same finding enough, round over round, that no fixed
    character-similarity cutoff reliably converges against it - see traceability.md
    for the real-world evidence. For this specific check (has this skill already
    told us about this location before?), same-location-and-category is treated as
    sufficient on its own. Title similarity is kept as an additional, looser path
    so a same-titled finding from a *different* category can still be caught (the
    cross-category case remains a documented limitation - see test_dedupe.py).
    This is deliberately not applied to `collapse_duplicates`, which dedupes
    findings *within* one run: two distinct concerns from the same skill at nearby
    lines in a single call are a real, if uncommon, case that should not be
    silently merged just because they share a category.
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
