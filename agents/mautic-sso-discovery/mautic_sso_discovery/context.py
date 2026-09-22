"""Loads the bundled, fixed Moneta SSO contract into one string for the
discovery agent's system prompt. These files are static copies from
awais786/sso-rules-moneta (see
docs/superpowers/specs/2026-09-22-mautic-sso-discovery-agent-design.md) -
not fetched at runtime, since the contract is fixed for every discovery run
regardless of which target repo is being investigated.
"""
from __future__ import annotations

from pathlib import Path

_CONTEXT_DIR = Path(__file__).resolve().parent.parent / "context"
_CONTEXT_FILES = ["authentication.md", "apps-overview.md", "proxy-auth-middleware-spec.md"]


def load_moneta_contract() -> str:
    sections = [f"## Source: {name}\n\n{(_CONTEXT_DIR / name).read_text()}" for name in _CONTEXT_FILES]
    return "\n\n---\n\n".join(sections)
