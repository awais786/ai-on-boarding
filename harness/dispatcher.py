"""Tool dispatcher: the harness's enforcement point.

Every tool call the agent wants to make goes through `Dispatcher.dispatch`.
The allowed_tools policy is checked here, and only here — not in AGENTS.md,
not in the tool implementations, and not as a second hard-coded list.

Because it is the one chokepoint, it is also where dispatch decisions are
logged: a denial is a WARNING, ordinary traffic is INFO.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .config import HarnessConfig
from .tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)

_MAX_LOGGED_CHARS = 120


def _short(value: Any) -> str:
    """Render a value for a log line, capped so file contents and long commands
    can't flood the log (or dump their whole payload into it)."""
    text = repr(value)
    if len(text) <= _MAX_LOGGED_CHARS:
        return text
    return f"{text[:_MAX_LOGGED_CHARS]}… ({len(text)} chars)"


def _format_call(tool_name: str, kwargs: dict) -> str:
    args = ", ".join(f"{key}={_short(val)}" for key, val in kwargs.items())
    return f"{tool_name}({args})"


@dataclass
class ToolResult:
    tool_name: str
    ok: bool
    output: Any = None
    error: str | None = None


class Dispatcher:
    def __init__(self, config: HarnessConfig, registry: dict | None = None):
        self._config = config
        self._registry = TOOL_REGISTRY if registry is None else registry

    def dispatch(self, tool_name: str, **kwargs) -> ToolResult:
        if not self._config.is_allowed(tool_name):
            allowed = ", ".join(self._config.allowed_tools) or "(none configured)"
            logger.warning(
                "denied %s: not in allowed_tools (allowed: %s)", tool_name, allowed
            )
            return ToolResult(
                tool_name=tool_name,
                ok=False,
                error=(
                    f"Tool '{tool_name}' is not permitted by the harness. "
                    f"Allowed tools: {allowed}."
                ),
            )

        tool_fn = self._registry.get(tool_name)
        if tool_fn is None:
            logger.error(
                "cannot run %s: permitted by allowed_tools but no implementation "
                "is registered", tool_name
            )
            return ToolResult(
                tool_name=tool_name,
                ok=False,
                error=f"Tool '{tool_name}' is allowed but has no implementation.",
            )

        logger.info("allowed %s — running", _format_call(tool_name, kwargs))
        try:
            output = tool_fn(**kwargs)
        except Exception as exc:  # tool-level failure, distinct from a policy denial
            logger.warning("%s failed: %s", tool_name, exc)
            return ToolResult(tool_name=tool_name, ok=False, error=str(exc))

        logger.info("%s succeeded -> %s", tool_name, _short(output))
        return ToolResult(tool_name=tool_name, ok=True, output=output)
