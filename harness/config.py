"""Harness configuration: which tools the runtime permits.

This is a capability list the harness enforces, not an instruction to the agent
(that's AGENTS.md's job). Loaded from YAML so the allowlist is data, not code
baked into the dispatcher.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


@dataclass
class HarnessConfig:
    allowed_tools: list[str] = field(default_factory=list)

    def is_allowed(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools


def load_config(path: str | None = None) -> HarnessConfig:
    resolved = path or DEFAULT_CONFIG_PATH
    with open(resolved, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    config = HarnessConfig(allowed_tools=list(raw.get("allowed_tools") or []))
    logger.info(
        "loaded allowlist from %s: %s",
        resolved,
        ", ".join(config.allowed_tools) or "(none configured)",
    )
    return config
