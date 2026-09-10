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

from .validate import Check

DEFAULT_POLICY_PATH = os.path.join(os.path.dirname(__file__), "policy.yaml")


class _Blanks(dict):
    """Unsupplied prompt placeholders render empty rather than raising."""

    def __missing__(self, key):
        return ""


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

    def render(self, **fields: str) -> str:
        return self.prompt.format_map(_Blanks(fields)).strip()


@dataclass
class Policy:
    phases: list[Phase] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    # Guardrail: how many times the harness will hand failing checks back to
    # the agent before giving up. 0 disables recovery entirely.
    max_repair_attempts: int = 0
    repair: Phase | None = None


def _phase(entry: dict, tools: list[str], mode: str, model: str | None) -> Phase:
    return Phase(
        name=entry.get("name") or "phase",
        prompt=entry.get("prompt") or "{task}",
        allowed_tools=list(entry.get("allowed_tools") or tools),
        permission_mode=entry.get("permission_mode") or mode,
        model=entry.get("model") or model,
    )


def load_policy(path: str | None = None) -> Policy:
    resolved = path or DEFAULT_POLICY_PATH
    with open(resolved, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    tools = list(raw.get("allowed_tools") or [])
    mode = raw.get("permission_mode") or "acceptEdits"
    model = raw.get("model") or None

    repair_entry = raw.get("repair")
    return Policy(
        phases=[_phase(e, tools, mode, model) for e in raw.get("phases") or []],
        checks=[
            Check(
                name=c.get("name") or "check",
                command=list(c.get("command") or []),
                cwd=c.get("cwd") or ".",
            )
            for c in raw.get("checks") or []
        ],
        max_repair_attempts=int(raw.get("max_repair_attempts") or 0),
        repair=_phase(repair_entry, tools, mode, model) if repair_entry else None,
    )


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
