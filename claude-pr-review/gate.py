"""Layer 4: render Layer 3's verified findings as the Ready to merge: yes/no
verdict - a finding blocks only if it still carries a citation. Exits
non-zero on "no" so CI can fail the check.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _line(f: dict) -> str:
    if not f.get("file"):
        loc = "no location"
    elif f.get("line") is None:
        loc = f["file"]
    else:
        loc = f"{f['file']}:{f['line']}"
    return f"- [{f['severity']}] {f['summary']} ({loc})"


def render(findings: dict) -> tuple[str, bool]:
    all_findings = findings.get("findings", [])
    blocking = [f for f in all_findings if f.get("citation")]
    nits = [f for f in all_findings if not f.get("citation")]
    ready = not blocking

    lines = ["# PR Review Verdict", ""]
    if blocking:
        lines.append("## Blocking findings")
        for f in blocking:
            lines.append(_line(f) + f" - cites: {f['citation']}")
        lines.append("")
    if nits:
        lines.append("## Nits (non-blocking)")
        for f in nits:
            lines.append(_line(f))
        lines.append("")
    if not all_findings:
        lines.append("No findings.")
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
