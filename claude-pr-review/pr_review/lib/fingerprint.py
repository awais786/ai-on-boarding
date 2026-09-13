"""Content-addressed finding identity, so a finding the author already
answered can be recognized across pushes even as line numbers drift.

No line number in the key: it shifts on unrelated edits above it, so it's
carried alongside only as a re-anchoring hint (see state.py's resolve()).
"""
from __future__ import annotations

import hashlib
import re

_COMMENT_RE = re.compile(r"#.*$", re.M)


def normalize_snippet(s: str) -> str:
    s = _COMMENT_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def fingerprint(finding: dict, snippet: str) -> str:
    """Coerces null `file`/`line` (a repo-level finding) to empty strings so
    it still gets a stable identity instead of crashing.
    """
    key = "|".join([
        finding.get("source") or "model",
        finding.get("file") or "",
        finding.get("category") or finding.get("citation") or "",
        normalize_snippet(snippet),
    ])
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def short_id(fp: str) -> str:
    """First 8 chars, shown to humans (dismissal checkboxes, comment text)."""
    return fp[:8]
