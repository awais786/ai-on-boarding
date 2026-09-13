"""Layer 4: render Layer 3's verified findings as the Ready to merge: yes/no
verdict. A finding blocks if it is cited and CRITICAL/MAJOR, or if it is a
CRITICAL that Layer 3 independently confirmed without one - see
severity.is_blocking() for why those are different kinds of evidence.
Everything else at CRITICAL/MAJOR, and any unverified finding, gets its own
"worth a look" section instead of being buried among MINOR nits. Exits
non-zero on "no" so CI can fail the check.

Also enforces invariant 4 (CLAUDE.md): Layer 3 may escalate a severity,
never downgrade one. A violation is repaired upward and reported, not
raised - see _enforce_severity_floor().
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pr_review.lib import fingerprint, severity, state


def _enforce_severity_floor(all_findings: list[dict]) -> tuple[list[dict], int]:
    """Invariant 4 (CLAUDE.md): Layer 3 may escalate a severity, never
    downgrade one. A violation is repaired UPWARD rather than raised - a
    raise here kills the run before post.py writes anything, so the review
    that caught a downgrade would be the one review nobody ever sees. The
    count is surfaced in the verdict so the repair is never silent.

    Not an `assert`: `python -O` strips those, which would drop the
    backstop exactly where it is meant to be load-bearing.
    """
    out, violations = [], 0
    for f in all_findings:
        floor = f.get("l2_severity", f.get("severity"))
        if severity.RANK.get(f.get("severity"), 0) < severity.RANK.get(floor, 0):
            f = {**f, "severity": floor}
            violations += 1
        out.append(f)
    return out, violations


SEVERITY_DOT = {"CRITICAL": "🔴", "MAJOR": "🟠", "MINOR": "🟡"}

# A safety net, not the fix: judge.md is what asks for a short summary. A
# model that ignores it shouldn't get to publish a ten-line paragraph into
# a list a reviewer is meant to skim.
SUMMARY_MAX_CHARS = 220


def _short(text: str | None, limit: int = SUMMARY_MAX_CHARS) -> str:
    collapsed = " ".join((text or "").split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1].rstrip() + "…"


def _location(f: dict) -> str:
    if not f.get("file"):
        return "no location"
    return f["file"] if f.get("line") is None else f"{f['file']}:{f['line']}"


def _line(f: dict) -> str:
    tag = " `unverified`" if f.get("unverified") else ""
    if f.get("resurfaced"):
        # Dismissed once, but now judged more severe than what was waived.
        tag += " `resurfaced`"
    dot = SEVERITY_DOT.get(f.get("severity"), "⚪")
    return f"- {dot} **{f['severity']}**{tag} {_short(f.get('summary'))} — `{_location(f)}`"


def render_finding_comment(f: dict) -> str:
    """One finding as its own inline review comment, anchored to its line.

    Deliberately short: the reader is looking at the code it refers to, so
    the location and the surrounding context don't need restating.
    """
    dot = SEVERITY_DOT.get(f.get("severity"), "⚪")
    lines = [f"{dot} **{f['severity']}** — {_short(f.get('summary'))}"]
    if f.get("citation"):
        lines.append(f"\n> cites: {_short(f['citation'], 160)}")
    elif f.get("verified"):
        lines.append("\n> no citation — blocking on Layer 3's independent verification")
    if f.get("unverified"):
        lines.append("\n> verification unavailable — severity left as Layer 2 set it")
    return "\n".join(lines)


def render(findings: dict) -> tuple[str, bool]:
    all_findings, floor_violations = _enforce_severity_floor(findings.get("findings", []))

    # Dismissed or resolved findings are records, not live concerns - kept
    # out of the blocking/serious/nits computation entirely.
    dismissed = [f for f in all_findings if f.get("status") == "dismissed"]
    resolved = [f for f in all_findings if f.get("status") == "resolved"]
    live = [f for f in all_findings if f not in dismissed and f not in resolved]

    blocking = [f for f in live if severity.is_blocking(f)]
    serious = [
        f for f in live
        if f not in blocking
        and (f.get("severity") in severity.BLOCKING_SEVERITIES or f.get("unverified"))
    ]
    nits = [f for f in live if f not in blocking and f not in serious]

    # A review that didn't run can't say "ready" - a green verdict from a
    # Layer 2 that errored out would look like a genuinely clean review.
    layer2_error = findings.get("layer2_error")
    ready = not blocking and not layer2_error

    lines = ["# PR Review Verdict", ""]
    if layer2_error:
        lines.append(
            "> **Review incomplete.** Layer 2 could not run, so this verdict reflects "
            "Layer 1 (lint) only and cannot be read as a clean review. Re-run the check "
            f"once the cause is cleared.\n>\n> `{layer2_error}`"
        )
        lines.append("")
    if blocking:
        lines.append("## Blocking (%d)" % len(blocking))
        for f in blocking:
            # An uncited blocker earns its place from Layer 3's independent
            # check, so say that instead of printing "cites: None".
            basis = (
                f"<br>  ↳ cites: `{_short(f['citation'], 160)}`" if f.get("citation")
                else "<br>  ↳ no citation — verified by Layer 3"
            )
            lines.append(_line(f) + basis)
        lines.append("")
    if serious:
        lines.append("## Unblocked but worth a look (%d)" % len(serious))
        for f in serious:
            lines.append(_line(f))
        lines.append("")
    if nits:
        lines.append("## Nits (%d)" % len(nits))
        for f in nits:
            # A nit with a fingerprint renders as a dismiss checkbox.
            # Blocking/serious findings never get this - not how a real
            # concern gets waived.
            if f.get("fp"):
                lines.append(state.render_dismissal_line(f))
            else:
                lines.append(_line(f))
        if any(f.get("fp") for f in nits):
            lines.append("_Tick a box to dismiss that finding; the reviewer won't raise it again._")
        lines.append("")
    if dismissed:
        lines.append("<details><summary>Previously dismissed (%d)</summary>" % len(dismissed))
        lines.append("")
        for f in dismissed:
            lines.append(state.render_dismissal_line(f))
        lines.append("")
        lines.append("</details>")
        lines.append("")
    if resolved:
        lines.append("<details><summary>Resolved (%d)</summary>" % len(resolved))
        lines.append("")
        for f in resolved:
            lines.append(f"- `{fingerprint.short_id(f['fp'])}` {f.get('severity', '')} {f.get('summary', '')} (code no longer found)")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    if not all_findings:
        lines.append("No findings.")
        lines.append("")
    suppressed = findings.get("suppressed_count") or 0
    if suppressed:
        lines.append(f"_{suppressed} additional finding(s) suppressed by the findings cap._")
    unverified_count = sum(1 for f in all_findings if f.get("unverified"))
    if unverified_count:
        lines.append(f"_Verification unavailable for {unverified_count} finding(s) - see [unverified] above._")
    rejected = findings.get("rejected_count") or 0
    if rejected:
        lines.append(f"_{rejected} finding(s) dropped by Layer 3 as unsupported._")
    if floor_violations:
        lines.append(
            f"_{floor_violations} finding(s) had a severity below Layer 2's and were "
            "restored to it - Layer 3 may escalate a severity, never lower one._"
        )
    if suppressed or unverified_count or rejected or floor_violations:
        lines.append("")
    lines.append(f"**Ready to merge: {'yes' if ready else 'no'}**")
    return "\n".join(lines), ready


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--findings", type=Path, required=True, help="Path to verify.py's output JSON")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    findings = json.loads(args.findings.read_text())
    report, ready = render(findings)

    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report)
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
