"""Shared fixtures for the hook tests."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from protect_sensitive_files import (  # noqa: E402  pylint: disable=wrong-import-position
    BREAK_GLASS_ENV,
)


@pytest.fixture(autouse=True)
def _no_ambient_pylint_override(monkeypatch):
    """Run every test with the PYLINT override off.

    Same reasoning as the break-glass fixture below: the variable can be set for
    the whole session by settings.json, and a stale or wrong value turned the
    resolver tests into failures about the environment rather than the code.
    Tests that exercise the override set it themselves.
    """
    monkeypatch.delenv("PYLINT", raising=False)


@pytest.fixture(autouse=True)
def _no_ambient_break_glass(monkeypatch):
    """Run every test with the break-glass override off.

    Without this the suite quietly changes meaning depending on how the session was
    launched: with CLAUDE_HOOKS_ALLOW_PROTECTED set, every expected denial becomes a
    warning and the block tests fail. Tests that exercise the override set it
    themselves. Subprocesses inherit os.environ, so this covers the end-to-end tests
    too.
    """
    monkeypatch.delenv(BREAK_GLASS_ENV, raising=False)
