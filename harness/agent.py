"""Agent creation/invocation.

An Agent is a dispatcher bound to a loaded HarnessConfig. `call_tool` is the
only path from "the agent wants to call a tool" to a tool implementation, and
it always passes through the dispatcher's allowlist check first.
"""
from __future__ import annotations

from . import enable_verbose_logging
from .config import load_config
from .dispatcher import Dispatcher, ToolResult


class Agent:
    def __init__(self, dispatcher: Dispatcher):
        self._dispatcher = dispatcher

    def call_tool(self, tool_name: str, **kwargs) -> ToolResult:
        return self._dispatcher.dispatch(tool_name, **kwargs)


def create_agent(config_path: str | None = None, verbose: bool = False) -> Agent:
    if verbose:
        enable_verbose_logging()
    return Agent(Dispatcher(load_config(config_path)))
