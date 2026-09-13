"""Memory across pushes. State lives inside the agent's own sticky PR
comment as an HTML-commented JSON block - auditable, needs no external
store, and survives force-push since carry_forward() keys off content
(blob SHA), not a commit range. Pure module; post.py reads/writes the
actual comment.

Shape of the state dict:
    {
        "schema": 1,
        "head": "<sha>",
        "files": {"<path>": "<blob-sha>", ...},
        "findings": [
            {"fp": "<16-hex fingerprint>", "status": "open"|"dismissed"|"resolved",
             "severity": "...", "file": "...", "line": <int|None>,
             "snippet": "...", "summary": "...", "first_seen": "<sha>",
             "verified": bool},
            ...
        ],
    }
"""
from __future__ import annotations

import json
import re

from pr_review.lib import fingerprint, severity

MARKER = "pr-review-agent:state:v1"

_STATE_RE = re.compile(rf"<!-- {re.escape(MARKER)}\n(.*?)\n-->", re.S)
_TICK_RE = re.compile(r"^- \[x\] `([0-9a-f]{8})`", re.M | re.I)
_UNTICK_RE = re.compile(r"^- \[ \] `([0-9a-f]{8})`", re.M | re.I)


def render(state: dict) -> str:
    return f"\n<!-- {MARKER}\n{json.dumps(state, separators=(',', ':'))}\n-->"


def parse(comment_body: str) -> dict | None:
    """Corrupt or missing state degrades to a cold start - never raises,
    never fails the job. Valid JSON that isn't an object also counts as
    corrupt, since callers do `.get(...)` on the result.
    """
    match = _STATE_RE.search(comment_body)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def render_dismissal_line(f: dict) -> str:
    box = "[x]" if f.get("status") == "dismissed" else "[ ]"
    sid = fingerprint.short_id(f.get("fp") or "")
    loc = f["file"] if f.get("file") else "no location"
    if f.get("file") and f.get("line") is not None:
        loc = f"{f['file']}:{f['line']}"
    return f"- {box} `{sid}` {f.get('severity', '')} `{loc}` - {f.get('summary', '')}"


def apply_dismissals(comment_body: str, findings: list[dict]) -> list[dict]:
    """Read the comment's checkbox ticks and mark matching findings
    dismissed. Must be called with the comment body fetched immediately
    before it is next written - see post.py.

    A tick is only ever honoured for a non-blocking finding - see
    severity.is_blocking(). A finding without a fingerprint is passed
    through untouched. Un-ticking a dismissed finding means "raise this
    again"; an id both ticked and un-ticked resolves toward showing it.
    """
    ticked = {m.lower() for m in _TICK_RE.findall(comment_body)}
    unticked = {m.lower() for m in _UNTICK_RE.findall(comment_body)}
    dismissed_ids = ticked - unticked
    out = []
    for f in findings:
        f = dict(f)
        fp = f.get("fp")
        if fp and f.get("status") == "dismissed" and fingerprint.short_id(fp).lower() in unticked:
            f["status"] = "open"
            f.pop("dismissed_at_severity", None)
            out.append(f)
            continue
        if fp and fingerprint.short_id(fp).lower() in dismissed_ids:
            if severity.is_blocking(f):
                # gate.py renders a checkbox for nits only, so a tick naming
                # a blocking finding was hand-added to the comment body.
                # Honouring it would let anyone who can post a comment on the
                # PR clear the merge gate: fingerprints are derived from the
                # author's own code, so the id is computable in advance.
                ceiling = f.get("dismissed_at_severity")
                if ceiling and severity.RANK.get(f["severity"], 0) > severity.RANK.get(ceiling, 0):
                    # Legitimately waived once, at a lower severity - say so,
                    # or it reads as the agent ignoring a dismissal.
                    f["resurfaced"] = True
                f["status"] = "open"
                out.append(f)
                continue
            ceiling = f.get("dismissed_at_severity")
            if ceiling and severity.RANK.get(f.get("severity"), 0) > severity.RANK.get(ceiling, 0):
                # Judged worse than what was waived - reopen rather than
                # let a stale tick suppress a now-more-severe finding.
                f["status"] = "open"
                f["resurfaced"] = True
            else:
                f["status"] = "dismissed"
                # Severity isn't part of the fingerprint, so record what was
                # actually waived or the dismissal would apply at any severity.
                f.setdefault("dismissed_at_severity", f.get("severity"))
        out.append(f)
    return out


def carry_forward(prior_state: dict | None, current_blobs: dict[str, str]) -> tuple[list[dict], set[str]]:
    """Which prior OPEN findings survive to this push, and which files are
    untouched since the prior run - matched by blob SHA (survives
    rebase/squash/force-push, unlike a commit-range diff).

    Dismissed findings aren't returned here - see carried_dismissals().
    """
    if not prior_state:
        return [], set()
    prior_files = prior_state.get("files", {})
    unchanged = {path for path, sha in current_blobs.items() if prior_files.get(path) == sha}
    carried = [
        f for f in prior_state.get("findings", [])
        if f.get("file") in unchanged and f.get("status") == "open"
    ]
    return carried, unchanged


def carried_dismissals(prior_state: dict | None) -> list[dict]:
    """Every finding a human has dismissed, carried forward unconditionally
    - no file/freshness condition, since the fingerprint already encodes
    the code and changes with it if the code changes materially.

    Keeping these in state is what makes dismissal durable across pushes
    that don't happen to re-raise the finding.
    """
    if not prior_state:
        return []
    return [f for f in prior_state.get("findings", []) if f.get("status") == "dismissed"]


def resolve(entry: dict, new_content: str, window: int = 30) -> tuple[str, int | None]:
    """Re-anchor a carried finding whose file changed. Search near the
    recorded line first, widen to the whole file, and mark resolved only if
    the snippet can't be found anywhere.

    Slides a same-sized window of lines rather than checking one at a time,
    since a multi-line normalized target can't be a substring of one line.

    A finding with no snippet (a repo/file-level claim, `line` is null)
    stays open rather than being declared resolved - "can't check" and
    "code is gone" are different answers.
    """
    original_snippet = entry.get("snippet") or ""
    target = fingerprint.normalize_snippet(original_snippet)
    if not target:
        return "open", entry.get("line")
    lines = new_content.splitlines()
    span = max(1, len(original_snippet.splitlines()))

    def _search(indices):
        for i in indices:
            end = i + span
            if end > len(lines):
                continue
            window_text = fingerprint.normalize_snippet("\n".join(lines[i:end]))
            if target in window_text:
                return i + (span // 2) + 1  # roughly the window's center, 1-indexed
        return None

    old_line = entry.get("line")
    if old_line is not None:
        near = range(max(0, old_line - 1 - window), min(len(lines), old_line - 1 + window + 1))
        found = _search(near)
        if found is not None:
            return "open", found

    found = _search(range(len(lines)))
    if found is not None:
        return "open", found
    return "resolved", None
