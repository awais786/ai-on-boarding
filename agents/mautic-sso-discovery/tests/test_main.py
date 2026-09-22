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
    called = {}

    def fake_run_discover(target_repo, out_path, workdir):
        called["args"] = (target_repo, out_path)

    monkeypatch.setattr("mautic_sso_discovery.__main__.run_discover", fake_run_discover)
    out_path = tmp_path / "r.md"
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "discover", "--target-repo", "https://x", "--out", str(out_path)],
    )

    assert main() == 0
    assert called["args"] == ("https://x", out_path)


def test_propose_issues_dispatches_to_run_propose_issues(monkeypatch, tmp_path):
    called = {}

    def fake_run_propose_issues(report_path, github_repo, client):
        called["args"] = (report_path, github_repo)
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
    assert called["args"] == (report_path, "x/y")
