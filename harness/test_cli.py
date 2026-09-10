"""Tests for the entry point's argument handling.

All use --dry-run, so the agent is never invoked.
"""
from __future__ import annotations

from harness.__main__ import main


def test_dry_run_reports_success_without_invoking_the_agent(capsys):
    exit_code = main(["Add login", "--dry-run"])

    assert exit_code == 0
    assert "agent not invoked" in capsys.readouterr().out


def test_cli_model_overrides_the_policy_file(capsys):
    main(["Add login", "--model", "opus", "--dry-run"])

    out = capsys.readouterr().out
    assert "model = opus" in out
    assert "--model opus" in out


def test_without_the_flag_no_model_is_forced(capsys):
    main(["Add login", "--dry-run"])

    out = capsys.readouterr().out
    assert "model = (agent default)" in out
    assert "--model" not in out


def test_policy_file_supplies_the_model_when_no_flag_is_given(capsys, tmp_path):
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text("allowed_tools: [Read]\nmodel: sonnet\n")

    main(["Add login", "--policy", str(policy_file), "--dry-run"])

    assert "--model sonnet" in capsys.readouterr().out
