"""Single CI entrypoint for a PR push. Replaces three separate
judge.py/verify.py/gate.py steps with one script so state can flow between
them:

  1. Read the sticky comment (if any) -> prior_state. Corrupt/missing state
     cold-starts.
  2. Diff prior_state.files against this push's file blob SHAs: unchanged
     files carry their prior open findings forward as-is (Layer 3 skipped);
     changed files re-anchor each finding by snippet search - found nearby
     stays open, not found marks resolved.
  3. judge.judge(..., carried=carried) - Layer 2 sees carried findings as
     "already raised, do not repeat" but still reviews the whole diff.
  4. verify.verify() on judge's NEW findings only.
  5. Every new finding gets a fingerprint so a future push can recognize
     and carry it forward.
  6. post.post() re-fetches the comment fresh, reconciles any dismissal
     tick made since this job started, then renders and PATCHes/POSTs -
     one render per run, using the same reconciled data that gets written.

Files/snippets for re-anchoring are read from the local checkout
(target.REPO_ROOT), not fetched from GitHub.
"""
from __future__ import annotations

import argparse
import sys

import anthropic

from pr_review.ci import github, post
from pr_review.core import agent, target
from pr_review.lib import fingerprint, severity, state
from pr_review.pipeline import judge, verify

REPO_ROOT = target.REPO_ROOT
SNIPPET_CONTEXT_LINES = 2


def fetch_prior_state(repo: str, pr: str) -> dict | None:
    comments = github.pr_comments(repo, pr)
    comment_id = post.find_existing_comment_id(comments)
    if comment_id is None:
        return None
    body = next(c["body"] for c in comments if c["id"] == comment_id)
    return state.parse(body)


def _read_file(path: str) -> str | None:
    full = REPO_ROOT / path
    if not full.is_file():
        return None
    return full.read_text(errors="replace")


def _snippet_for(file: str | None, line: int | None) -> str:
    # No file/line means a repo- or file-level claim - no snippet to
    # anchor to; state.resolve() knows an empty one isn't "code is gone".
    if not file or line is None:
        return ""
    content = _read_file(file)
    if content is None:
        return ""
    lines = content.splitlines()
    start = max(0, line - 1 - SNIPPET_CONTEXT_LINES)
    end = min(len(lines), line + SNIPPET_CONTEXT_LINES)
    return "\n".join(lines[start:end])


def reanchor_changed_files(prior_state: dict | None, unchanged: set[str]) -> tuple[list[dict], list[dict]]:
    """For every prior open finding NOT covered by the fast unchanged-file
    path, try to re-find its snippet in the current file content. Returns
    (re_anchored_open, resolved).
    """
    if not prior_state:
        return [], []
    open_elsewhere = [
        f for f in prior_state.get("findings", [])
        if f.get("status") == "open" and f.get("file") not in unchanged
    ]
    re_anchored, resolved = [], []
    for f in open_elsewhere:
        if not f.get("file"):
            # Nothing to re-read or resolve against - carry it forward as-is.
            re_anchored.append({**f, "status": "open"})
            continue
        content = _read_file(f["file"])
        if content is None:
            resolved.append({**f, "status": "resolved"})
            continue
        status, new_line = state.resolve(f, content)
        if status == "open":
            re_anchored.append({**f, "line": new_line, "status": "open"})
        else:
            resolved.append({**f, "status": "resolved"})
    return re_anchored, resolved


STATUS_RANK = {"resolved": 0, "open": 1, "dismissed": 2}


def _dismissal_ceiling(*entries: dict) -> str | None:
    """The severity a dismissal was actually made at, if one of these
    entries is dismissed. Falls back to the entry's own severity, for state
    written before `dismissed_at_severity` existed.
    """
    for e in entries:
        if e.get("status") == "dismissed":
            return e.get("dismissed_at_severity") or e.get("severity")
    return None


def dedupe_findings(*groups: list[dict]) -> list[dict]:
    """Collapse entries describing the same finding (same fingerprint) into
    one, across every source they can arrive from - needed because Layer 2
    may legitimately re-raise something a carried entry already covers.

    Precedence: CONTENT comes from the latest group (callers order
    oldest-to-freshest), taken as a whole dict so severity/l2_severity
    never mix across runs. STATUS takes the strongest claim by
    STATUS_RANK (dismissed > open > resolved - a human decision is sticky).
    `first_seen` keeps the earliest value.

    Entries with no fingerprint pass through untouched - no identity to
    group on.
    """
    out: list[dict] = []
    position: dict[str, int] = {}
    for group in groups:
        for f in group:
            fp = f.get("fp")
            if not fp:
                out.append(dict(f))
                continue
            if fp not in position:
                position[fp] = len(out)
                out.append(dict(f))
                continue
            existing = out[position[fp]]
            merged = dict(f)  # later group wins the content
            status = max(
                (existing.get("status"), f.get("status")),
                key=lambda s: STATUS_RANK.get(s, 1),
            )
            ceiling = _dismissal_ceiling(existing, f)
            if ceiling:
                # Needed so apply_dismissals() can refuse re-applying a
                # stale tick to something that has since got worse.
                merged["dismissed_at_severity"] = ceiling
                if severity.RANK.get(merged.get("severity"), 0) > severity.RANK.get(ceiling, 0):
                    # A dismissal covers what was dismissed, not an
                    # escalation of it.
                    status = "open"
                    merged["resurfaced"] = True
            merged["status"] = status
            first_seen = existing.get("first_seen") or f.get("first_seen")
            if first_seen:
                merged["first_seen"] = first_seen
            out[position[fp]] = merged
    return out


def attach_metadata(findings: list[dict]) -> list[dict]:
    """Stamp every fresh finding with a fingerprint and the snippet it was
    computed from - state.resolve() searches for this exact snippet on a
    future push to re-anchor the finding.
    """
    out = []
    for f in findings:
        f = dict(f)
        snippet = _snippet_for(f.get("file"), f.get("line"))
        f["fp"] = fingerprint.fingerprint(f, snippet)
        f["snippet"] = snippet
        f.setdefault("status", "open")
        out.append(f)
    return out


def run(client, repo: str, pr: str, head_sha: str) -> dict:
    prior_state = fetch_prior_state(repo, pr)
    current_blobs = github.pr_file_blobs(repo, pr)

    carried, unchanged = state.carry_forward(prior_state, current_blobs)
    re_anchored, resolved = reanchor_changed_files(prior_state, unchanged)
    dismissed = state.carried_dismissals(prior_state)
    all_carried = carried + re_anchored

    # Fetched once and handed to both layers: two separate fetches let a
    # push landing mid-run give Layer 2 and Layer 3 different diffs.
    diff = target.get_diff(pr)
    rules = target.repo_rules()

    judge_result = judge.judge(client, pr, diff, rules, carried=all_carried)
    new_findings = judge_result.get("findings", [])
    verified = verify.verify(client, diff, rules, {"findings": new_findings})

    new_with_metadata = attach_metadata(verified.get("findings", []))
    for f in all_carried:
        f.setdefault("status", "open")

    # Oldest to freshest: this push's judgment wins on content, dedupe
    # keeps the strongest status (dismissal survives a fresh re-raise).
    combined = dedupe_findings(resolved, dismissed, all_carried, new_with_metadata)
    base_state = {
        "schema": 1, "head": head_sha, "files": current_blobs,
        "suppressed_count": judge_result.get("suppressed_count", 0),
        "rejected_count": verified.get("rejected_count", 0),
    }
    if judge_result.get("layer2_error"):
        # gate.render() refuses "ready" when the reviewing layer never ran.
        base_state["layer2_error"] = judge_result["layer2_error"]
    # gate.render() happens inside post.post(), against findings freshly
    # reconciled against the live comment - not here, which would use
    # dismissal state stale by the time the comment is written.
    return post.post(repo, pr, combined, base_state)


def log_usage() -> None:
    """What this review cost, to the CI log (stderr) - not to the PR, which
    would put a dollar figure in front of every author. The USD is an
    estimate from agent.PRICING; the token counts are exact. A cached-read
    count of 0 across a multi-call run means prompt caching silently broke.
    """
    usage = agent.USAGE
    if not usage["calls"]:
        return
    print(
        f"[run] {usage['calls']} model call(s) | "
        f"{usage['input_tokens']:,} in / {usage['output_tokens']:,} out | "
        f"{usage['cache_read_input_tokens']:,} cached read, "
        f"{usage['cache_creation_input_tokens']:,} cache write | "
        f"~${usage['usd']:.4f} (estimate)",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--pr", required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()

    client = anthropic.Anthropic()
    try:
        result = run(client, args.repo, args.pr, args.head_sha)
    finally:
        # In a finally: a run that dies posting the comment has still spent
        # the whole review's tokens, and that is exactly when you want to
        # know what it cost.
        log_usage()
    print(result["report"])
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
