"""Accuracy eval for the four reasoning spokes in reasoning.py, run against
the real Anthropic API. NOT part of pytest - test_reasoning.py mocks the
model's response, so it verifies retry/parsing plumbing but can't catch a
prompts.py wording change that degrades the model's actual judgment. This
script catches that, at the cost of live, billed API calls (100 per run: 25
cases per spoke).

Run by hand, typically before/after touching prompts.py:

    ANTHROPIC_API_KEY=... python -m issue_reconciler.evals

Prints one markdown table (one row per case, with the model's own reasoning)
plus per-spoke and overall pass counts - paste the table straight into a PR
description as the results summary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from issue_reconciler.reasoning import (
    MODEL,
    activity_check,
    completion_check,
    reference_validation,
    stale_or_superseded_check,
)
from issue_reconciler.types import LinkedPR

# Local dev only, same as __main__.py: no-op in CI, where ANTHROPIC_API_KEY
# is already a real env var.
load_dotenv(Path(__file__).parent / ".env")

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


def _pr(**overrides: object) -> LinkedPR:
    base: LinkedPR = {
        "number": 1,
        "title": "",
        "state": "OPEN",
        "merged": False,
        "merged_at": None,
        "is_draft": False,
        "head_ref_name": "x",
        "updated_at": "2026-09-01T00:00:00+00:00",
        "review_decision": None,
    }
    return {**base, **overrides}  # type: ignore[return-value]


# Each case: (name, issue_title, ...spoke-specific args..., expected verdict value)

COMPLETION_CASES = [
    ("single merged PR clearly fixes it", "Login crashes when the password field is left empty",
     [_pr(title="Fix crash when password field is left empty on login", merged=True)], True),
    ("unrelated PR referencing the issue by mistake", "Add dark mode toggle to settings page",
     [_pr(title="Fix typo in README", merged=True)], False),
    ("only one of several needed changes", "Support CSV and JSON export for reports",
     [_pr(title="Add CSV export for reports", merged=True)], False),
    ("two merged PRs together fully resolve it", "Add pagination to the user list API",
     [_pr(number=1, title="Add page/size query params to user list endpoint", merged=True),
      _pr(number=2, title="Add pagination metadata to user list response", merged=True)], True),
    ("matching PR not merged yet", "Fix flaky test in test_orchestrator.py",
     [_pr(title="Fix flaky test in test_orchestrator.py by freezing time", merged=False)], False),
    ("relevant PR merged alongside an irrelevant one", "Fix crash when uploading a file larger than 10MB",
     [_pr(number=1, title="Fix crash when uploading a file larger than 10MB", merged=True),
      _pr(number=2, title="Update contributor guidelines", merged=True)], True),
    ("no linked PR actually addresses the issue", "Add OAuth login support",
     [_pr(number=1, title="Fix typo in login page copy", merged=True),
      _pr(number=2, title="Update CI runner image version", merged=True),
      _pr(number=3, title="Reformat code with black", merged=True)], False),
    ("two relevant PRs plus one irrelevant, relevant ones resolve it", "Add rate limiting to the public API",
     [_pr(number=1, title="Add per-IP rate limiting middleware", merged=True),
      _pr(number=2, title="Add rate limit response headers", merged=True),
      _pr(number=3, title="Fix Makefile typo", merged=True)], True),
    ("multiple partial PRs, none complete", "Support import, export, and backup of user data",
     [_pr(number=1, title="Add data import from CSV", merged=True),
      _pr(number=2, title="Add data export to CSV", merged=True)], False),
    ("paraphrased match resolves it", "Fix null pointer exception in report generator",
     [_pr(title="Fix NPE thrown by report generator on an empty dataset", merged=True)], True),
    ("shares keywords but different feature", "Add search filter to dashboard",
     [_pr(title="Add sort control to dashboard", merged=True)], False),
    ("performance issue fixed via caching", "Reduce dashboard load time",
     [_pr(title="Add response caching to dashboard endpoint", merged=True)], False),
    ("only backend half of a UI+backend issue done", "Add CSV export button with download UI",
     [_pr(title="Add CSV export API endpoint", merged=True)], False),
    ("two PRs each handle one half of a compound ask", "Support both light and dark themes",
     [_pr(number=1, title="Add light theme support", merged=True),
      _pr(number=2, title="Add dark theme support", merged=True)], True),
    ("issue asks for tests, PR adds them", "Add test coverage for the hashing module",
     [_pr(title="Add unit tests for issue_reconciler.hashing", merged=True)], True),
    ("issue asks to remove deprecated code, PR removes it", "Remove deprecated v1 API endpoints",
     [_pr(title="Remove deprecated /v1/* endpoints", merged=True)], True),
    ("security issue, unrelated formatting PR", "Fix SQL injection vulnerability in search endpoint",
     [_pr(title="Reformat code with black", merged=True)], False),
    ("rate limiting PR matches rate limiting issue", "Add per-IP rate limiting to the public API",
     [_pr(title="Add per-IP rate limiting middleware to the public API", merged=True)], True),
    ("connection leak PR matches memory leak issue", "Fix memory leak in the worker pool",
     [_pr(title="Fix connection leak by closing DB sessions in the worker pool", merged=True)], True),
    ("startup validation PR matches config validation issue", "Add config validation on startup",
     [_pr(title="Add startup validation for required environment variables", merged=True)], True),
    ("connection pooling is only part of a full DB migration", "Migrate the database from SQLite to Postgres",
     [_pr(title="Add Postgres connection pooling", merged=True)], False),
    ("one of two requested languages", "Add French and Spanish translations",
     [_pr(title="Add French translations", merged=True)], False),
    ("off-by-one fix matches pagination bug report", "Fix broken pagination links on the last page",
     [_pr(title="Fix off-by-one error in pagination link generation", merged=True)], True),
    ("unrelated feature PR", "Add two-factor authentication for login",
     [_pr(title="Add password strength meter to the signup form", merged=True)], False),
    ("dedup fix matches duplicate-entries report", "Fix duplicate entries in the export CSV",
     [_pr(title="Deduplicate rows before writing the export CSV", merged=True)], True),
]

ACTIVITY_CASES = [
    ("no review, updated today", "Fix race condition in state writer",
     _pr(title="Fix race condition in state writer", updated_at="2026-09-14T00:00:00+00:00"), "active"),
    ("no review, updated 3 days ago", "Add retry logic for transient GitHub API errors",
     _pr(title="Add retry logic for transient GitHub API errors", updated_at="2026-09-11T00:00:00+00:00"), "active"),
    ("no review, updated 10 days ago", "Fix flaky integration test in CI",
     _pr(title="Fix flaky integration test in CI", updated_at="2026-09-04T00:00:00+00:00"), "abandoned"),
    ("no review, updated 28 days ago", "Add structured logging to orchestrator",
     _pr(title="Add structured logging to orchestrator", updated_at="2026-08-17T00:00:00+00:00"), "abandoned"),
    ("no review, updated 45 days ago", "Fix incorrect timezone handling in run log",
     _pr(title="Fix incorrect timezone handling in run log", updated_at="2026-07-31T00:00:00+00:00"), "abandoned"),
    ("no review, updated 105 days ago", "Add dry-run summary output",
     _pr(title="Add dry-run summary output", updated_at="2026-06-01T00:00:00+00:00"), "abandoned"),
    ("no review, updated 250 days ago", "Add unit tests for hashing module",
     _pr(title="Add unit tests for hashing module", updated_at="2026-01-08T00:00:00+00:00"), "abandoned"),
    ("approved, updated yesterday", "Add pagination metadata to user list response",
     _pr(title="Add pagination metadata to user list response", updated_at="2026-09-13T00:00:00+00:00", review_decision="APPROVED"), "active"),
    ("approved, updated a week ago", "Remove deprecated v1 API endpoints",
     _pr(title="Remove deprecated v1 API endpoints", updated_at="2026-09-07T00:00:00+00:00", review_decision="APPROVED"), "active"),
    ("approved, updated 20 days ago", "Add config validation on startup",
     _pr(title="Add config validation on startup", updated_at="2026-08-25T00:00:00+00:00", review_decision="APPROVED"), "abandoned"),
    ("approved, updated 25 days ago", "Fix broken pagination links on last page",
     _pr(title="Fix broken pagination links on last page", updated_at="2026-08-20T00:00:00+00:00", review_decision="APPROVED"), "abandoned"),
    ("approved, updated 60 days ago", "Fix memory leak in worker pool",
     _pr(title="Fix memory leak in worker pool", updated_at="2026-07-16T00:00:00+00:00", review_decision="APPROVED"), "abandoned"),
    ("approved, updated 180 days ago", "Migrate database from SQLite to Postgres",
     _pr(title="Migrate database from SQLite to Postgres", updated_at="2026-03-18T00:00:00+00:00", review_decision="APPROVED"), "abandoned"),
    ("review requested, updated today", "Fix off-by-one error in date range filter",
     _pr(title="Fix off-by-one error in date range filter", updated_at="2026-09-14T00:00:00+00:00", review_decision="REVIEW_REQUIRED"), "active"),
    ("review requested, updated a week ago", "Fix duplicate entries in export CSV",
     _pr(title="Fix duplicate entries in export CSV", updated_at="2026-09-07T00:00:00+00:00", review_decision="REVIEW_REQUIRED"), "blocked"),
    ("review requested, updated 14 days ago", "Add per-IP rate limiting to public API",
     _pr(title="Add per-IP rate limiting to public API", updated_at="2026-08-31T00:00:00+00:00", review_decision="REVIEW_REQUIRED"), "blocked"),
    ("review requested, updated 28 days ago", "Add two-factor authentication for login",
     _pr(title="Add two-factor authentication for login", updated_at="2026-08-17T00:00:00+00:00", review_decision="REVIEW_REQUIRED"), "blocked"),
    ("review requested, updated 90 days ago", "Support multiple linked PRs per issue",
     _pr(title="Support multiple linked PRs per issue", updated_at="2026-06-16T00:00:00+00:00", review_decision="REVIEW_REQUIRED"), "abandoned"),
    ("review requested, updated 200 days ago", "Improve lease expiry handling",
     _pr(title="Improve lease expiry handling", updated_at="2026-02-26T00:00:00+00:00", review_decision="REVIEW_REQUIRED"), "abandoned"),
    ("changes requested, updated yesterday", "Add French and Spanish translations",
     _pr(title="Add French and Spanish translations", updated_at="2026-09-13T00:00:00+00:00", review_decision="CHANGES_REQUESTED"), "blocked"),
    ("changes requested, updated 5 days ago", "Fix SQL injection vulnerability in search endpoint",
     _pr(title="Fix SQL injection vulnerability in search endpoint", updated_at="2026-09-09T00:00:00+00:00", review_decision="CHANGES_REQUESTED"), "blocked"),
    ("changes requested, updated 15 days ago", "Improve error message when GitHub token is invalid",
     _pr(title="Improve error message when GitHub token is invalid", updated_at="2026-08-30T00:00:00+00:00", review_decision="CHANGES_REQUESTED"), "blocked"),
    ("changes requested, updated 25 days ago", "Reduce GitHub API rate limit usage",
     _pr(title="Reduce GitHub API rate limit usage", updated_at="2026-08-20T00:00:00+00:00", review_decision="CHANGES_REQUESTED"), "blocked"),
    ("changes requested, updated 40 days ago", "Add caching layer for GitHub GraphQL queries",
     _pr(title="Add caching layer for GitHub GraphQL queries", updated_at="2026-08-05T00:00:00+00:00", review_decision="CHANGES_REQUESTED"), "blocked"),
    ("long silence after changes requested", "Reduce GitHub API rate limit usage",
     _pr(title="Reduce GitHub API rate limit usage", updated_at="2026-05-01T00:00:00+00:00", review_decision="CHANGES_REQUESTED"), "blocked"),
]

REFERENCE_CASES = [
    ("title clearly matches", "Fix race condition in state writer",
     _pr(title="Fix race condition in state writer when two workers run concurrently"), True),
    ("loosely worded but same intent", "Improve error message when GitHub token is invalid",
     _pr(title="Add clearer error message for invalid GitHub token"), True),
    ("matches via paraphrase", "Add retry logic for transient GitHub API errors",
     _pr(title="Retry GitHub API calls on 5xx errors"), True),
    ("dedup fix matches duplicate report", "Fix duplicate entries in export CSV",
     _pr(title="Deduplicate rows before writing export CSV"), True),
    ("rate limiting PR matches rate limiting issue", "Add per-IP rate limiting to public API",
     _pr(title="Add per-IP rate limiting middleware to public API"), True),
    ("removal PR matches removal issue", "Remove deprecated v1 API endpoints",
     _pr(title="Remove deprecated /v1/* endpoints"), True),
    ("connection leak PR matches memory leak issue", "Fix memory leak in worker pool",
     _pr(title="Fix connection leak by closing DB sessions in worker pool"), True),
    ("startup validation PR matches config validation issue", "Add config validation on startup",
     _pr(title="Add startup validation for required environment variables"), True),
    ("off-by-one fix matches pagination bug report", "Fix broken pagination links on last page",
     _pr(title="Fix off-by-one error in pagination link generation"), True),
    ("test PR matches test coverage issue", "Add unit tests for hashing module",
     _pr(title="Add unit tests for issue_reconciler.hashing"), True),
    ("title clearly unrelated", "Add email notification on reconciliation failure",
     _pr(title="Update dependency versions in requirements.txt"), False),
    ("wrong issue number, unrelated title", "Support multiple linked PRs per issue",
     _pr(title="Fix typo in changelog"), False),
    ("dark mode issue, README typo PR", "Add dark mode toggle to settings page",
     _pr(title="Fix typo in README"), False),
    ("2FA issue, unrelated signup PR", "Add two-factor authentication for login",
     _pr(title="Add password strength meter to signup form"), False),
    ("security issue, unrelated formatting PR", "Fix SQL injection vulnerability in search endpoint",
     _pr(title="Reformat code with black"), False),
    ("migration issue, unrelated CI PR", "Migrate database from SQLite to Postgres",
     _pr(title="Update CI runner image version"), False),
    ("translation issue, unrelated test PR", "Add French and Spanish translations",
     _pr(title="Fix flaky integration test in CI"), False),
    ("logging issue, unrelated dependency bump", "Add structured logging to orchestrator",
     _pr(title="Bump anthropic SDK to latest version"), False),
    ("lease issue, unrelated docs PR", "Improve lease expiry handling",
     _pr(title="Add contributor guidelines to README"), False),
    ("timezone issue, unrelated formatting PR", "Fix incorrect timezone handling in run log",
     _pr(title="Add HTML formatting to writers"), False),
    ("same goal, different mechanism word", "Add rate limiting to public API",
     _pr(title="Add per-user request quota to public API"), True),
    ("matches issue intent without repeating its wording", "Fix flaky test in test_orchestrator.py",
     _pr(title="Freeze time in orchestrator tests to remove flakiness"), True),
    ("shares the goal but wrong API surface", "Add caching layer for GitHub GraphQL queries",
     _pr(title="Add in-memory cache for GitHub REST API responses"), False),
    ("labels feature implemented via query filtering", "Support custom labels in reconciliation rules",
     _pr(title="Add label filtering to the GitHub issue query"), True),
    ("same intent via a different technique", "Reduce GitHub API rate limit usage",
     _pr(title="Batch GitHub API requests to cut call volume"), True),
]

STALE_CASES = [
    ("two merged PRs build on each other", "Add pagination to the user list API",
     [_pr(number=1, title="Add page/size query params to user list endpoint", state="MERGED", merged_at="2026-09-05T00:00:00+00:00", merged=True),
      _pr(number=2, title="Add pagination metadata to user list response", state="MERGED", merged_at="2026-09-08T00:00:00+00:00", merged=True)], False),
    ("sequential fix and its test coverage, not a replacement", "Fix crash in orchestrator on empty issue list",
     [_pr(number=1, title="Fix crash in orchestrator on empty issue list", state="MERGED", merged_at="2026-09-05T00:00:00+00:00", merged=True),
      _pr(number=2, title="Add test coverage for orchestrator crash fix", state="MERGED", merged_at="2026-09-06T00:00:00+00:00", merged=True)], False),
    ("each PR adds a distinct requested format", "Support CSV and JSON export for reports",
     [_pr(number=1, title="Add CSV export for reports", state="MERGED", merged_at="2026-09-01T00:00:00+00:00", merged=True),
      _pr(number=2, title="Add JSON export for reports", state="MERGED", merged_at="2026-09-03T00:00:00+00:00", merged=True)], False),
    ("middleware plus its response headers, complementary", "Add rate limiting to public API",
     [_pr(number=1, title="Add per-IP rate limiting middleware", state="MERGED", merged_at="2026-09-01T00:00:00+00:00", merged=True),
      _pr(number=2, title="Add rate limit response headers", state="MERGED", merged_at="2026-09-04T00:00:00+00:00", merged=True)], False),
    ("retry logic plus error logging, complementary", "Improve error handling in orchestrator",
     [_pr(number=1, title="Add retry for transient GitHub errors", state="MERGED", merged_at="2026-09-01T00:00:00+00:00", merged=True),
      _pr(number=2, title="Add structured error logging", state="MERGED", merged_at="2026-09-05T00:00:00+00:00", merged=True)], False),
    ("each PR adds a distinct requested language", "Add multi-language support",
     [_pr(number=1, title="Add French translations", state="MERGED", merged_at="2026-09-01T00:00:00+00:00", merged=True),
      _pr(number=2, title="Add Spanish translations", state="MERGED", merged_at="2026-09-03T00:00:00+00:00", merged=True)], False),
    ("hashing approach replaces the abandoned cache attempt", "Fix duplicate email notifications for the same issue",
     [_pr(number=1, title="Add in-memory dedup cache for email notifications", state="CLOSED", merged_at=None),
      _pr(number=2, title="Fix duplicate email notifications by hashing issue+PR pair before sending", state="MERGED", merged_at="2026-09-10T00:00:00+00:00", merged=True)], True),
    ("GraphQL switch replaces the closed caching attempt", "Reduce GitHub API rate limit usage",
     [_pr(number=1, title="Cache GitHub API responses in memory", state="CLOSED", merged_at=None),
      _pr(number=2, title="Switch to GitHub GraphQL API to reduce rate limit usage", state="MERGED", merged_at="2026-09-11T00:00:00+00:00", merged=True)], True),
    ("rewrite replaces the closed retry-wrapper attempt", "Fix flaky integration test in CI",
     [_pr(number=1, title="Add retry wrapper around flaky test", state="CLOSED", merged_at=None),
      _pr(number=2, title="Rewrite flaky test to remove timing dependency", state="MERGED", merged_at="2026-09-09T00:00:00+00:00", merged=True)], True),
    ("server-side caching replaces the closed client-side attempt", "Reduce dashboard load time",
     [_pr(number=1, title="Add client-side caching for dashboard", state="CLOSED", merged_at=None),
      _pr(number=2, title="Add server-side response caching for dashboard", state="MERGED", merged_at="2026-09-08T00:00:00+00:00", merged=True)], True),
    ("context-manager rewrite replaces the closed GC-tuning attempt", "Fix memory leak in worker pool",
     [_pr(number=1, title="Increase worker pool GC frequency", state="CLOSED", merged_at=None),
      _pr(number=2, title="Rewrite worker pool to use context managers for cleanup", state="MERGED", merged_at="2026-09-07T00:00:00+00:00", merged=True)], True),
    ("direct Postgres rewrite replaces the closed migration script", "Migrate database from SQLite to Postgres",
     [_pr(number=1, title="Add a SQLite-to-Postgres migration script", state="CLOSED", merged_at=None),
      _pr(number=2, title="Rewrite storage layer directly against Postgres, dropping SQLite", state="MERGED", merged_at="2026-09-12T00:00:00+00:00", merged=True)], True),
    ("only one linked PR - nothing to supersede it (fix)", "Fix crash in orchestrator on empty issue list",
     [_pr(number=1, title="Fix crash in orchestrator on empty issue list", state="MERGED", merged_at="2026-09-05T00:00:00+00:00", merged=True)], False),
    ("only one linked PR - nothing to supersede it (config)", "Add config validation on startup",
     [_pr(number=1, title="Add startup validation for required environment variables", state="MERGED", merged_at="2026-09-05T00:00:00+00:00", merged=True)], False),
    ("only one linked PR - nothing to supersede it (pagination bug)", "Fix broken pagination links on last page",
     [_pr(number=1, title="Fix off-by-one error in pagination link generation", state="MERGED", merged_at="2026-09-05T00:00:00+00:00", merged=True)], False),
    ("only one linked PR - nothing to supersede it (tests)", "Add unit tests for hashing module",
     [_pr(number=1, title="Add unit tests for issue_reconciler.hashing", state="MERGED", merged_at="2026-09-05T00:00:00+00:00", merged=True)], False),
    ("three PRs: a later rewrite supersedes an earlier closed attempt", "Add rate limiting to public API",
     [_pr(number=1, title="Add per-IP rate limiting middleware", state="CLOSED", merged_at=None),
      _pr(number=2, title="Add sliding-window rate limiter", state="MERGED", merged_at="2026-09-06T00:00:00+00:00", merged=True),
      _pr(number=3, title="Add rate limit response headers", state="MERGED", merged_at="2026-09-09T00:00:00+00:00", merged=True)], True),
    ("three PRs: all sequentially build on the same cache", "Add caching layer for GitHub GraphQL queries",
     [_pr(number=1, title="Add in-memory cache for GraphQL responses", state="MERGED", merged_at="2026-09-01T00:00:00+00:00", merged=True),
      _pr(number=2, title="Add cache TTL configuration", state="MERGED", merged_at="2026-09-04T00:00:00+00:00", merged=True),
      _pr(number=3, title="Add cache invalidation on webhook events", state="MERGED", merged_at="2026-09-07T00:00:00+00:00", merged=True)], False),
    ("three PRs: a full schema rewrite supersedes the incremental attempts", "Migrate database from SQLite to Postgres",
     [_pr(number=1, title="Add Postgres connection pooling", state="MERGED", merged_at="2026-09-01T00:00:00+00:00", merged=True),
      _pr(number=2, title="Add SQLite compatibility shim", state="CLOSED", merged_at=None),
      _pr(number=3, title="Migrate schema and drop SQLite entirely", state="MERGED", merged_at="2026-09-10T00:00:00+00:00", merged=True)], True),
    ("three PRs: each adds a distinct requested capability", "Support import, export, and backup of user data",
     [_pr(number=1, title="Add data import from CSV", state="MERGED", merged_at="2026-09-01T00:00:00+00:00", merged=True),
      _pr(number=2, title="Add data export to CSV", state="MERGED", merged_at="2026-09-03T00:00:00+00:00", merged=True),
      _pr(number=3, title="Add scheduled backup of user data", state="MERGED", merged_at="2026-09-06T00:00:00+00:00", merged=True)], False),
    ("merged rewrite replaces a still-open, stalled attempt", "Fix memory leak in worker pool",
     [_pr(number=1, title="Add manual GC trigger to worker pool", state="OPEN", merged_at=None, updated_at="2026-07-01T00:00:00+00:00"),
      _pr(number=2, title="Rewrite worker pool using context managers to fix the leak", state="MERGED", merged_at="2026-09-10T00:00:00+00:00", merged=True)], True),
    ("simpler merged cache replaces a still-open Redis attempt", "Add caching layer for GitHub GraphQL queries",
     [_pr(number=1, title="Add Redis-backed cache for GraphQL queries", state="OPEN", merged_at=None, updated_at="2026-07-15T00:00:00+00:00"),
      _pr(number=2, title="Add lightweight in-memory cache for GraphQL queries", state="MERGED", merged_at="2026-09-09T00:00:00+00:00", merged=True)], True),
    ("merged PR complements a still-open, still-relevant PR", "Add pagination to the user list API",
     [_pr(number=1, title="Add page/size query params to user list endpoint", state="OPEN", merged_at=None, updated_at="2026-09-10T00:00:00+00:00"),
      _pr(number=2, title="Add pagination metadata to user list response", state="MERGED", merged_at="2026-09-11T00:00:00+00:00", merged=True)], False),
    ("merged PR covers a different piece, open PR still needed", "Support custom labels in reconciliation rules",
     [_pr(number=1, title="Add label field to rule schema", state="OPEN", merged_at=None, updated_at="2026-09-08T00:00:00+00:00"),
      _pr(number=2, title="Add label filtering to the GitHub issue query", state="MERGED", merged_at="2026-09-09T00:00:00+00:00", merged=True)], False),
    ("merged PR tackles a different aspect than a stalled, still-open attempt", "Reduce dashboard load time",
     [_pr(number=1, title="Add client-side caching for dashboard", state="OPEN", merged_at=None, updated_at="2026-06-01T00:00:00+00:00"),
      _pr(number=2, title="Rewrite dashboard queries to fix N+1 lookups", state="MERGED", merged_at="2026-09-10T00:00:00+00:00", merged=True)], False),
]


def _escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _score(spoke: str, name: str, key: str, expected: object, verdict: dict | None) -> dict:
    if verdict is None:
        return {"spoke": spoke, "case": name, "expected": expected, "actual": None, "ok": False, "reasoning": "no verdict returned"}
    return {
        "spoke": spoke,
        "case": name,
        "expected": expected,
        "actual": verdict[key],
        "ok": verdict[key] == expected,
        "reasoning": verdict["reasoning"],
    }


def main() -> int:
    client = anthropic.Anthropic()
    rows: list[dict] = []

    for name, issue_title, linked_prs, expected in COMPLETION_CASES:
        verdict = completion_check(client, issue_title, linked_prs)
        rows.append(_score("completion_check", name, "fully_resolved", expected, verdict))

    for name, issue_title, pr, expected in ACTIVITY_CASES:
        verdict = activity_check(client, issue_title, pr, NOW)
        rows.append(_score("activity_check", name, "status", expected, verdict))

    for name, issue_title, pr, expected in REFERENCE_CASES:
        verdict = reference_validation(client, issue_title, pr)
        rows.append(_score("reference_validation", name, "matches", expected, verdict))

    for name, issue_title, linked_prs, expected in STALE_CASES:
        verdict = stale_or_superseded_check(client, issue_title, linked_prs)
        rows.append(_score("stale_or_superseded_check", name, "superseded", expected, verdict))

    print(f"Model: {MODEL}\n")
    print("| Spoke | Case | Expected | Actual | Result | Reasoning |")
    print("|---|---|---|---|---|---|")
    for row in rows:
        mark = "\u2713" if row["ok"] else "\u2717"
        print(
            f"| {row['spoke']} | {_escape(row['case'])} | {row['expected']!r} | "
            f"{row['actual']!r} | {mark} | {_escape(row['reasoning'])} |"
        )

    print()
    for spoke in ("completion_check", "activity_check", "reference_validation", "stale_or_superseded_check"):
        spoke_rows = [r for r in rows if r["spoke"] == spoke]
        print(f"{spoke}: {sum(r['ok'] for r in spoke_rows)}/{len(spoke_rows)}")

    total_ok = sum(r["ok"] for r in rows)
    print(f"\nTotal: {total_ok}/{len(rows)} correct")
    return 0 if total_ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
