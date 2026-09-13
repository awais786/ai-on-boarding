"""Post the run's verdict as a sticky PR comment - find-and-PATCH the prior
one by state.MARKER rather than POSTing a new comment every push.

Ordering matters: the comment body is fetched fresh in post(), as the LAST
read before deciding what to write, not reused from an earlier copy - a
stale copy could overwrite a dismissal tick made after this job started.
gate.render() happens here too, against the reconciled findings, so the
posted text and the stored state always come from the same render.
"""
from __future__ import annotations

import os
import sys

from pr_review.ci import github
from pr_review.lib import severity, state
from pr_review.pipeline import gate

MAX_COMMENT_CHARS = 65_536  # GitHub's hard cap on an issue comment body
TRUNCATION_NOTICE = "\n\n_Verdict truncated to fit GitHub's comment size limit._\n"

# Alias kept so callers catching a failure to reach GitHub don't need to
# know which module raises it.
PostError = github.GitHubError


# The account the reviewer posts as, when that isn't a Bot. In CI with
# GITHUB_TOKEN the author is github-actions[bot] and this is unnecessary;
# set it for a local run or a PAT, whose comments are authored by a User
# and would otherwise never be recognised as the agent's own - leaving a
# fresh duplicate comment on every push instead of one sticky one.
#
# Safe because it is trusted CONFIG, set by whoever runs the reviewer. It
# is never read from a comment, so a PR author can't nominate themselves.
TRUSTED_COMMENT_AUTHOR = os.environ.get("PR_REVIEW_COMMENT_AUTHOR", "").strip()


def _is_bot(comment: dict) -> bool:
    user = comment.get("user") or {}
    if str(user.get("type", "")).lower() == "bot":
        return True
    return bool(TRUSTED_COMMENT_AUTHOR) and user.get("login") == TRUSTED_COMMENT_AUTHOR


def find_existing_comment_id(comments: list[dict]):
    """The sticky comment to update, or None to post a fresh one.

    Only a BOT-authored comment counts. The marker is public text: anyone
    who can comment on the PR can paste it, and adopting such a comment
    would make the agent read its prior state - and its dismissal ticks -
    from a stranger, then PATCH the verdict into their comment. A human
    quoting the verdict copies the marker too, which is the benign version
    of the same thing.

    Outside CI the reviewer's own comments are authored by a User, not a
    Bot - set PR_REVIEW_COMMENT_AUTHOR to that login so they are still
    recognised, or every push leaves another duplicate comment.
    """
    bot_matches = [
        c for c in comments
        if state.MARKER in (c.get("body") or "") and _is_bot(c)
    ]
    return bot_matches[-1]["id"] if bot_matches else None


def build_comment_body(verdict_report: str, new_state: dict) -> str:
    return verdict_report + "\n" + state.render(new_state)


STORED_SUMMARY_CHARS = 200


def _without_status(s: dict, status: str) -> dict:
    out = dict(s)
    out["findings"] = [f for f in s.get("findings", []) if f.get("status") != status]
    return out


def _with_trimmed_summaries(s: dict) -> dict:
    out = dict(s)
    out["findings"] = [
        {**f, "summary": f["summary"][:STORED_SUMMARY_CHARS] + "..."}
        if len(f.get("summary") or "") > STORED_SUMMARY_CHARS else f
        for f in s.get("findings", [])
    ]
    return out


def fit_to_comment_limit(new_state: dict) -> tuple[str, str, bool]:
    """Render the verdict and fit it under GitHub's comment cap.

    Cheapest loss first: as-is -> drop resolved entries -> trim stored
    summaries -> drop dismissed entries -> truncate the human-readable
    report -> shed entries least-severe-first. The JSON state block is
    never truncated mid-write: a half-written one parses as corrupt next
    run, taking every dismissal with it.
    """
    working = dict(new_state)
    stages = (
        lambda s: s,
        lambda s: _without_status(s, "resolved"),
        _with_trimmed_summaries,
        lambda s: _without_status(s, "dismissed"),
    )
    for transform in stages:
        working = transform(working)
        report, ready = gate.render(working)
        body = build_comment_body(report, working)
        if len(body) <= MAX_COMMENT_CHARS:
            return body, report, ready

    # Cut the prose, keep the (already trimmed) state block whole.
    tail = "\n" + state.render(working)
    budget = MAX_COMMENT_CHARS - len(tail) - len(TRUNCATION_NOTICE)
    if budget > 0:
        return report[:budget] + TRUNCATION_NOTICE + tail, report, ready

    # The trimmed state block alone still doesn't fit - reachable with a few
    # hundred carried OPEN findings, which no earlier stage drops. Shed
    # entries, least severe first, rather than emit a body GitHub rejects
    # outright: a rejected write means no verdict AND no state.
    findings = sorted(
        working.get("findings", []),
        key=lambda f: severity.RANK.get(f.get("severity"), 0),
        reverse=True,
    )
    while findings and budget <= 0:
        findings.pop()
        working = {**working, "findings": findings}
        tail = "\n" + state.render(working)
        budget = MAX_COMMENT_CHARS - len(tail) - len(TRUNCATION_NOTICE)
    report, ready = gate.render(working)
    return report[:max(0, budget)] + TRUNCATION_NOTICE + tail, report, ready


FINDING_MARKER = "pr-review-agent:finding"


def _finding_marker(fp: str) -> str:
    return f"<!-- {FINDING_MARKER}:{fp} -->"


def post_inline_comments(repo: str, pr: str, commit_sha: str, findings: list[dict]) -> int:
    """Anchor each located finding to its line, once.

    Skips anything already posted (matched on the fingerprint hidden in the
    body), anything without a file/line to anchor to, and anything already
    dismissed or resolved. Never raises: GitHub rejects a comment on a line
    outside the diff, and the summary comment is the complete record
    regardless, so a failure here costs presentation, not information.
    """
    try:
        existing = github.pr_review_comments(repo, pr)
    except github.GitHubError as exc:
        print(f"[post] could not list inline comments, skipping them: {exc}", file=sys.stderr)
        return 0

    already = {
        fp for c in existing
        for fp in [_fingerprint_in(c.get("body") or "")] if fp
    }
    posted = 0
    for f in findings:
        fp = f.get("fp")
        if not fp or fp in already or f.get("status") in ("dismissed", "resolved"):
            continue
        if not f.get("file") or f.get("line") is None:
            continue  # nothing to anchor to; it stays in the summary
        body = gate.render_finding_comment(f) + "\n\n" + _finding_marker(fp)
        try:
            github.create_review_comment(repo, pr, commit_sha, f["file"], f["line"], body)
            posted += 1
        except github.GitHubError as exc:
            print(f"[post] {exc}", file=sys.stderr)
    return posted


def _fingerprint_in(body: str) -> str | None:
    marker = f"<!-- {FINDING_MARKER}:"
    start = body.find(marker)
    if start == -1:
        return None
    end = body.find("-->", start)
    return body[start + len(marker):end].strip() if end != -1 else None


def post(repo: str, pr: str, combined_findings: list[dict], base_state: dict) -> dict:
    """Fetch the live comments, reconcile dismissal ticks, render the
    verdict, then PATCH the sticky comment or POST a new one. The caller's
    exit code must come from this return value, not an earlier render.
    """
    comments = github.pr_comments(repo, pr)
    comment_id = find_existing_comment_id(comments)
    live_body = next((c["body"] for c in comments if c.get("id") == comment_id), "")

    reconciled = state.apply_dismissals(live_body, combined_findings)
    new_state = dict(base_state)
    new_state["findings"] = reconciled
    body, report, ready = fit_to_comment_limit(new_state)

    if comment_id:
        github.update_comment(repo, comment_id, body)
    else:
        github.create_comment(pr, body)

    head = base_state.get("head")
    if head:
        posted = post_inline_comments(repo, pr, head, reconciled)
        if posted:
            print(f"[post] {posted} finding(s) commented inline", file=sys.stderr)
    return {"report": report, "ready": ready}
