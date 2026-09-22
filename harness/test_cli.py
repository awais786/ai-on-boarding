"""Tests for the entry point's argument handling.

All use --dry-run, so the agent is never invoked.
"""
from __future__ import annotations

from harness.__main__ import main


def test_dry_run_reports_every_phase_without_invoking_the_agent(capsys):
    exit_code = main(["Add login", "--dry-run"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "agent not invoked" in out
    assert "[plan]" in out and "[code]" in out and "[tests]" in out


def test_dry_run_shows_the_per_phase_models(capsys):
    main(["Add login", "--dry-run"])
    out = capsys.readouterr().out

    assert "--model opus" in out
    assert "--model haiku" in out
    assert "--model sonnet" in out


def test_planning_phase_is_launched_without_write_tools(capsys):
    main(["Add login", "--dry-run"])
    plan_block = capsys.readouterr().out.split("[code]")[0]

    assert "Read, Glob, Grep" in plan_block
    assert "Write" not in plan_block


def test_cli_model_overrides_every_phase(capsys):
    main(["Add login", "--model", "opus", "--dry-run"])
    out = capsys.readouterr().out

    assert out.count("--model opus") == 3
    assert "--model haiku" not in out


def test_policy_file_drives_the_phases(capsys, tmp_path):
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        'allowed_tools: [Read]\nphases:\n  - name: only\n    model: sonnet\n    prompt: "{task}"\n'
    )

    main(["Add login", "--policy", str(policy_file), "--dry-run"])
    out = capsys.readouterr().out

    assert "[only]" in out
    assert "[plan]" not in out
