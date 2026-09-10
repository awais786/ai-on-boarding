"""Tests for the execution policy the harness hands to the coding agent.

None of these invoke the agent: build_agent_command is pure, so the policy is
checkable without spending a token or touching the repository.
"""
from __future__ import annotations

import textwrap

from harness.policy import DEFAULT_POLICY_PATH, Policy, build_agent_command, load_policy


def test_shipped_policy_lists_the_six_permitted_tools():
    policy = load_policy()

    assert policy.allowed_tools == ["Read", "Glob", "Grep", "Edit", "Write", "Bash"]


def test_command_passes_the_allowlist_to_the_agent():
    policy = Policy(allowed_tools=["Read", "Bash"])

    command = build_agent_command("Add login", policy)

    assert "--allowedTools" in command
    index = command.index("--allowedTools")
    assert command[index + 1 : index + 3] == ["Read", "Bash"]


def test_command_carries_the_task_in_print_mode():
    command = build_agent_command("Add login", Policy(allowed_tools=["Read"]))

    assert command[0] == "claude"
    assert "-p" in command
    assert "Add login" in command


def test_configured_allowlist_is_used_not_hardcoded(tmp_path):
    """A policy file naming a different set must produce different flags."""
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        textwrap.dedent(
            """
            allowed_tools:
              - Read
            permission_mode: plan
            """
        )
    )

    policy = load_policy(str(policy_file))
    command = build_agent_command("Add login", policy)

    assert policy.allowed_tools == ["Read"]
    index = command.index("--allowedTools")
    assert command[index + 1] == "Read"
    assert "Bash" not in command
    assert command[command.index("--permission-mode") + 1] == "plan"


def test_empty_allowlist_omits_the_flag_rather_than_sending_nothing():
    """An empty --allowedTools would be a malformed invocation, not a lockdown."""
    command = build_agent_command("Add login", Policy(allowed_tools=[]))

    assert "--allowedTools" not in command


def test_default_policy_path_points_at_the_shipped_file():
    assert DEFAULT_POLICY_PATH.endswith("harness/policy.yaml")
