"""Tests for the execution policy the harness hands to the coding agent.

None of these invoke the agent: build_agent_command is pure, so the policy is
checkable without spending a token or touching the repository.
"""
from __future__ import annotations

import textwrap

from harness.policy import DEFAULT_POLICY_PATH, Phase, build_agent_command, load_policy


def write_policy(tmp_path, body: str) -> str:
    path = tmp_path / "policy.yaml"
    path.write_text(textwrap.dedent(body))
    return str(path)


def test_shipped_policy_runs_plan_then_code_then_tests():
    policy = load_policy()

    assert [p.name for p in policy.phases] == ["plan", "code", "tests"]


def test_shipped_policy_assigns_a_model_per_phase():
    models = {p.name: p.model for p in load_policy().phases}

    assert models == {"plan": "opus", "code": "haiku", "tests": "sonnet"}


def test_planning_phase_cannot_edit_or_run_commands():
    plan = next(p for p in load_policy().phases if p.name == "plan")

    assert plan.allowed_tools == ["Read", "Glob", "Grep"]
    for forbidden in ("Edit", "Write", "Bash"):
        assert forbidden not in plan.allowed_tools


def test_phases_inherit_the_default_allowlist_when_they_do_not_override():
    code = next(p for p in load_policy().phases if p.name == "code")

    assert code.allowed_tools == ["Read", "Glob", "Grep", "Edit", "Write", "Bash"]


def test_command_passes_that_phases_allowlist_to_the_agent():
    phase = Phase(name="code", prompt="{task}", allowed_tools=["Read", "Bash"])

    command = build_agent_command("Add login", phase)

    index = command.index("--allowedTools")
    assert command[index + 1 : index + 3] == ["Read", "Bash"]


def test_command_carries_the_prompt_in_print_mode():
    command = build_agent_command("Add login", Phase("code", "{task}", ["Read"]))

    assert command[0] == "claude"
    assert "-p" in command
    assert "Add login" in command


def test_model_is_passed_through_when_set():
    phase = Phase("code", "{task}", ["Read"], model="opus")

    command = build_agent_command("Add login", phase)

    assert command[command.index("--model") + 1] == "opus"


def test_no_model_flag_when_unset():
    """Unset must mean 'leave the agent's own default alone', not 'pick one'."""
    command = build_agent_command("Add login", Phase("code", "{task}", ["Read"]))

    assert "--model" not in command


def test_configured_policy_is_used_not_hardcoded(tmp_path):
    """A different policy file must produce different phases and flags."""
    path = write_policy(
        tmp_path,
        """
        allowed_tools: [Read]
        phases:
          - name: only
            model: haiku
            prompt: "{task}"
        """,
    )

    policy = load_policy(path)
    command = build_agent_command("Add login", policy.phases[0])

    assert [p.name for p in policy.phases] == ["only"]
    assert command[command.index("--model") + 1] == "haiku"
    assert "Bash" not in command


def test_prompt_receives_the_task_and_the_previous_phase_output():
    phase = Phase("code", "task={task} previous={previous}", ["Read"])

    rendered = phase.render(task="Add login", previous="the plan")

    assert rendered == "task=Add login previous=the plan"


def test_unsupplied_placeholder_renders_empty_rather_than_raising():
    """The repair prompt uses {failures}; the code prompt does not. A phase
    must not explode because a placeholder it never uses went unsupplied."""
    phase = Phase("code", "task={task} failures={failures}", ["Read"])

    assert phase.render(task="Add login") == "task=Add login failures="


def test_shipped_policy_defines_the_verification_layers():
    names = [c.name for c in load_policy().checks]

    assert names == ["django", "specs", "tests"]


def test_spec_check_validates_specs_not_in_progress_changes():
    """--all also validates openspec/changes/, where an unrelated failing
    change would make every harness run report FAIL."""
    specs = next(c for c in load_policy().checks if c.name == "specs")

    assert "--specs" in specs.command
    assert "--all" not in specs.command


def test_shipped_policy_caps_repair_attempts():
    policy = load_policy()

    assert policy.max_repair_attempts == 1
    assert policy.repair is not None


def test_repair_phase_can_edit_and_run_the_suite():
    repair = load_policy().repair

    assert "Edit" in repair.allowed_tools
    assert "Bash" in repair.allowed_tools


def test_recovery_is_off_when_the_policy_says_so(tmp_path):
    path = write_policy(
        tmp_path,
        """
        allowed_tools: [Read]
        phases:
          - name: only
            prompt: "{task}"
        """,
    )

    policy = load_policy(path)

    assert policy.max_repair_attempts == 0
    assert policy.repair is None


def test_empty_allowlist_omits_the_flag_rather_than_sending_nothing():
    """An empty --allowedTools would be a malformed invocation, not a lockdown."""
    command = build_agent_command("Add login", Phase("code", "{task}", []))

    assert "--allowedTools" not in command


def test_default_policy_path_points_at_the_shipped_file():
    assert DEFAULT_POLICY_PATH.endswith("harness/policy.yaml")
