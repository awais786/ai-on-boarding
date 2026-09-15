from __future__ import annotations

import sys

import issue_reconciler.__main__ as main_mod


def _fake_result(evidence_status="Todo"):
    evidence = {
        "issue_number": 1, "item_id": "PVTI_1", "current_status": evidence_status,
        "has_ignore_label": False, "linked_prs": [], "open_spec_proposals": ["x"],
        "last_status_actor": None, "last_status_at": None, "transition_count": 0,
    }
    return {
        "processed": [{"issue_number": 1, "issue_node_id": "I_1", "decision": {"action": "set_in_progress", "reason": "x"}, "evidence": evidence, "evidence_hash": "h", "skipped": None}],
        "failed": [], "lease_state": {}, "run_log": [], "circuit_broken": False,
    }


def test_dry_run_comments_but_does_not_mutate(monkeypatch, tmp_path):
    monkeypatch.setenv("BOARD_TOKEN", "t")
    monkeypatch.setattr(main_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(main_mod, "LEASES_PATH", tmp_path / "leases.json")
    monkeypatch.setattr(main_mod, "RUNLOG_PATH", tmp_path / "runlog.json")
    monkeypatch.setattr(main_mod, "GitHubClient", lambda token: "github-client")
    monkeypatch.setattr(main_mod.anthropic, "Anthropic", lambda: "anthropic-client")
    monkeypatch.setattr(main_mod.orchestrator, "validate_board_config", lambda client: None)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result())

    posted = {}
    monkeypatch.setattr(main_mod, "post_comment", lambda client, node_id, body: posted.setdefault("body", body))
    mutated = {"called": False}
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: mutated.__setitem__("called", True))

    monkeypatch.setattr(sys, "argv", ["main"])
    exit_code = main_mod.main()

    assert exit_code == 0
    assert "body" in posted
    assert mutated["called"] is False


def test_no_dry_run_also_mutates(monkeypatch, tmp_path):
    monkeypatch.setenv("BOARD_TOKEN", "t")
    monkeypatch.setattr(main_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(main_mod, "LEASES_PATH", tmp_path / "leases.json")
    monkeypatch.setattr(main_mod, "RUNLOG_PATH", tmp_path / "runlog.json")
    monkeypatch.setattr(main_mod, "GitHubClient", lambda token: "github-client")
    monkeypatch.setattr(main_mod.anthropic, "Anthropic", lambda: "anthropic-client")
    monkeypatch.setattr(main_mod.orchestrator, "validate_board_config", lambda client: None)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result())
    monkeypatch.setattr(main_mod, "post_comment", lambda *a, **k: None)
    mutated = {"called": False}
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: mutated.__setitem__("called", True))

    monkeypatch.setattr(sys, "argv", ["main", "--no-dry-run"])
    main_mod.main()

    assert mutated["called"] is True


def test_posts_slack_summary_when_webhook_configured_and_something_changed(monkeypatch, tmp_path):
    monkeypatch.setenv("BOARD_TOKEN", "t")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.setattr(main_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(main_mod, "LEASES_PATH", tmp_path / "leases.json")
    monkeypatch.setattr(main_mod, "RUNLOG_PATH", tmp_path / "runlog.json")
    monkeypatch.setattr(main_mod, "GitHubClient", lambda token: "github-client")
    monkeypatch.setattr(main_mod.anthropic, "Anthropic", lambda: "anthropic-client")
    monkeypatch.setattr(main_mod.orchestrator, "validate_board_config", lambda client: None)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result())
    monkeypatch.setattr(main_mod, "post_comment", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: None)

    posted = {}
    monkeypatch.setattr(main_mod, "post_summary", lambda url, text: posted.update(url=url, text=text))

    monkeypatch.setattr(sys, "argv", ["main"])
    main_mod.main()

    assert posted["url"] == "https://hooks.slack.test/x"
    assert "#1" in posted["text"]


def test_no_slack_post_without_a_webhook_url(monkeypatch, tmp_path):
    monkeypatch.setenv("BOARD_TOKEN", "t")
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(main_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(main_mod, "LEASES_PATH", tmp_path / "leases.json")
    monkeypatch.setattr(main_mod, "RUNLOG_PATH", tmp_path / "runlog.json")
    monkeypatch.setattr(main_mod, "GitHubClient", lambda token: "github-client")
    monkeypatch.setattr(main_mod.anthropic, "Anthropic", lambda: "anthropic-client")
    monkeypatch.setattr(main_mod.orchestrator, "validate_board_config", lambda client: None)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result())
    monkeypatch.setattr(main_mod, "post_comment", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: None)

    called = {"n": 0}
    monkeypatch.setattr(main_mod, "post_summary", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    monkeypatch.setattr(sys, "argv", ["main"])
    main_mod.main()

    assert called["n"] == 0
