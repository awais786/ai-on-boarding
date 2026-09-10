"""Execution policy: what the harness permits the coding agent to do.

The policy is data, translated into the coding agent's own permission flags.
Claude Code already gates tool use behind --allowedTools, so the harness's job
is to configure that mechanism, not to duplicate it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

DEFAULT_POLICY_PATH = os.path.join(os.path.dirname(__file__), "policy.yaml")


@dataclass
class Policy:
    allowed_tools: list[str] = field(default_factory=list)
    permission_mode: str = "acceptEdits"
    # None means "whatever the agent is already configured to use". The value
    # is passed through unvalidated: the agent owns the list of valid models,
    # and a copy of it here would go stale.
    model: str | None = None


def load_policy(path: str | None = None) -> Policy:
    resolved = path or DEFAULT_POLICY_PATH
    with open(resolved, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return Policy(
        allowed_tools=list(raw.get("allowed_tools") or []),
        permission_mode=raw.get("permission_mode") or "acceptEdits",
        model=raw.get("model") or None,
    )


def build_agent_command(
    task: str, policy: Policy, agent_bin: str = "claude"
) -> list[str]:
    """The exact argv the harness will run.

    Kept pure so the policy can be tested without invoking the agent.
    """
    command = [agent_bin, "-p", task, "--output-format", "json"]
    if policy.allowed_tools:
        command += ["--allowedTools", *policy.allowed_tools]
    if policy.permission_mode:
        command += ["--permission-mode", policy.permission_mode]
    if policy.model:
        command += ["--model", policy.model]
    return command
