"""Execution policy: what the harness permits the coding agent to do.

The policy is data, translated into the coding agent's own permission flags.
Claude Code already gates tool use behind --allowedTools and model choice
behind --model, so the harness's job is to configure those, not duplicate them.

A phase is one agent invocation. Phases inherit the top-level defaults and
override what they need, so "planning is read-only" and "coding runs on a
cheaper model" are policy edits rather than code changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

DEFAULT_POLICY_PATH = os.path.join(os.path.dirname(__file__), "policy.yaml")


@dataclass
class Phase:
    name: str
    prompt: str
    allowed_tools: list[str] = field(default_factory=list)
    permission_mode: str = "acceptEdits"
    # None means "whatever the agent is already configured to use". Passed
    # through unvalidated: the agent owns the set of valid models, and a copy
    # of that list here would go stale.
    model: str | None = None

    def render(self, task: str, previous: str = "") -> str:
        return self.prompt.format(task=task, previous=previous).strip()


@dataclass
class Policy:
    phases: list[Phase] = field(default_factory=list)


def load_policy(path: str | None = None) -> Policy:
    resolved = path or DEFAULT_POLICY_PATH
    with open(resolved, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    default_tools = list(raw.get("allowed_tools") or [])
    default_mode = raw.get("permission_mode") or "acceptEdits"
    default_model = raw.get("model") or None

    phases = []
    for entry in raw.get("phases") or []:
        phases.append(
            Phase(
                name=entry["name"],
                prompt=entry.get("prompt") or "{task}",
                allowed_tools=list(entry.get("allowed_tools") or default_tools),
                permission_mode=entry.get("permission_mode") or default_mode,
                model=entry.get("model") or default_model,
            )
        )
    return Policy(phases=phases)


def build_agent_command(
    prompt: str, phase: Phase, agent_bin: str = "claude"
) -> list[str]:
    """The exact argv the harness will run for one phase.

    Kept pure so the policy is checkable without invoking the agent.
    """
    command = [agent_bin, "-p", prompt, "--output-format", "json"]
    if phase.allowed_tools:
        command += ["--allowedTools", *phase.allowed_tools]
    if phase.permission_mode:
        command += ["--permission-mode", phase.permission_mode]
    if phase.model:
        command += ["--model", phase.model]
    return command
