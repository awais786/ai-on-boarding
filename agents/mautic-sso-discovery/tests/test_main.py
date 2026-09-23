from __future__ import annotations

from pathlib import Path

import pytest

from mautic_sso_discovery.__main__ import main


def test_discover_requires_target_repo_and_out(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "discover"])
    with pytest.raises(SystemExit):
        main()


def test_propose_issues_requires_report_and_github_repo(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "propose-issues"])
    with pytest.raises(SystemExit):
        main()


def test_discover_dispatches_to_run_discover(monkeypatch, tmp_path):
    monkeypatch.delenv("MAUTIC_DISCOVERY_MODEL", raising=False)
    called = {}

    def fake_run_discover(target_repo, out_path, workdir, *, model):
        called["args"] = (target_repo, out_path, model)

    monkeypatch.setattr("mautic_sso_discovery.__main__.run_discover", fake_run_discover)
    out_path = tmp_path / "r.md"
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "discover", "--target-repo", "https://x", "--out", str(out_path)],
    )

    assert main() == 0
    assert called["args"] == ("https://x", out_path, "claude-sonnet-5")


def test_discover_passes_through_custom_model_flag(monkeypatch, tmp_path):
    called = {}

    def fake_run_discover(target_repo, out_path, workdir, *, model):
        called["model"] = model

    monkeypatch.setattr("mautic_sso_discovery.__main__.run_discover", fake_run_discover)
    out_path = tmp_path / "r.md"
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "discover", "--target-repo", "https://x", "--out", str(out_path), "--model", "claude-haiku-4-5-20251001"],
    )

    assert main() == 0
    assert called["model"] == "claude-haiku-4-5-20251001"


def test_discover_default_model_comes_from_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("MAUTIC_DISCOVERY_MODEL", "claude-haiku-4-5-20251001")
    called = {}

    def fake_run_discover(target_repo, out_path, workdir, *, model):
        called["model"] = model

    monkeypatch.setattr("mautic_sso_discovery.__main__.run_discover", fake_run_discover)
    out_path = tmp_path / "r.md"
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "discover", "--target-repo", "https://x", "--out", str(out_path)],
    )

    assert main() == 0
    assert called["model"] == "claude-haiku-4-5-20251001"


def test_model_flag_overrides_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("MAUTIC_DISCOVERY_MODEL", "claude-haiku-4-5-20251001")
    called = {}

    def fake_run_discover(target_repo, out_path, workdir, *, model):
        called["model"] = model

    monkeypatch.setattr("mautic_sso_discovery.__main__.run_discover", fake_run_discover)
    out_path = tmp_path / "r.md"
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "discover", "--target-repo", "https://x", "--out", str(out_path), "--model", "claude-opus-5"],
    )

    assert main() == 0
    assert called["model"] == "claude-opus-5"


def test_propose_issues_dispatches_to_run_propose_issues(monkeypatch, tmp_path):
    monkeypatch.delenv("MAUTIC_DISCOVERY_MODEL", raising=False)
    called = {}

    def fake_run_propose_issues(report_path, github_repo, client, *, model, title_prefix):
        called["args"] = (report_path, github_repo, model, title_prefix)
        return {"A": "https://github.com/x/y/issues/1"}

    monkeypatch.setattr("mautic_sso_discovery.__main__.run_propose_issues", fake_run_propose_issues)
    monkeypatch.setattr("mautic_sso_discovery.__main__.GitHubClient", lambda token: "fake-client")
    monkeypatch.setenv("BOARD_TOKEN", "t")
    report_path = tmp_path / "report.md"
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "propose-issues", "--report", str(report_path), "--github-repo", "x/y"],
    )

    assert main() == 0
    assert called["args"] == (report_path, "x/y", "claude-sonnet-5", "")


def test_propose_issues_passes_through_title_prefix(monkeypatch, tmp_path):
    called = {}

    def fake_run_propose_issues(report_path, github_repo, client, *, model, title_prefix):
        called["title_prefix"] = title_prefix
        return {}

    monkeypatch.setattr("mautic_sso_discovery.__main__.run_propose_issues", fake_run_propose_issues)
    monkeypatch.setattr("mautic_sso_discovery.__main__.GitHubClient", lambda token: "fake-client")
    monkeypatch.setenv("BOARD_TOKEN", "t")
    report_path = tmp_path / "report.md"
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "propose-issues", "--report", str(report_path), "--github-repo", "x/y", "--title-prefix", "[TEST] "],
    )

    assert main() == 0
    assert called["title_prefix"] == "[TEST] "


def test_propose_issues_dry_run_drafts_without_creating_or_needing_a_token(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("BOARD_TOKEN", raising=False)
    called = {}

    def fake_draft_issues(report_path, *, model):
        called["args"] = (report_path, model)
        return [{"title": "A", "body": "body a", "depends_on": []}]

    def fail_if_called(*args, **kwargs):
        raise AssertionError("run_propose_issues must not be called in --dry-run mode")

    monkeypatch.setattr("mautic_sso_discovery.__main__.draft_issues", fake_draft_issues)
    monkeypatch.setattr("mautic_sso_discovery.__main__.run_propose_issues", fail_if_called)
    report_path = tmp_path / "report.md"
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "propose-issues", "--report", str(report_path), "--github-repo", "x/y", "--dry-run"],
    )

    assert main() == 0
    assert called["args"] == (report_path, "claude-sonnet-5")
    assert "[dry run] A" in capsys.readouterr().out
