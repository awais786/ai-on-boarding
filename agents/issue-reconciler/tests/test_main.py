from __future__ import annotations

import json
import sys

import issue_reconciler.__main__ as main_mod


def _fake_result(run_id="run-1", evidence_status="Todo", circuit_broken=False):
    evidence = {
        "issue_number": 1, "item_id": "PVTI_1", "current_status": evidence_status,
        "has_ignore_label": False, "linked_prs": [], "open_spec_proposals": ["x"],
        "last_status_actor": None, "last_status_at": None, "transition_count": 0,
    }
    return {
        "processed": [{"issue_number": 1, "issue_node_id": "I_1", "decision": {"action": "set_in_progress", "reason": "x"}, "evidence": evidence, "evidence_hash": "h", "skipped": None}],
        "failed": [],
        "lease_state": {},
        "run_log": [{"run_id": run_id, "issue_number": 1, "decision": "set_in_progress", "reason": "x", "evidence_hash": "h", "timestamp": "2026-09-16T00:00:00+00:00"}],
        "circuit_broken": circuit_broken,
    }


def _base_setup(monkeypatch, tmp_path):
    monkeypatch.setenv("BOARD_TOKEN", "t")
    monkeypatch.setattr(main_mod, "STATE_DIR", tmp_path)
    monkeypatch.setattr(main_mod, "LEASES_PATH", tmp_path / "leases.json")
    monkeypatch.setattr(main_mod, "RUNLOG_PATH", tmp_path / "runlog.json")
    monkeypatch.setattr(main_mod, "GitHubClient", lambda token: "github-client")
    monkeypatch.setattr(main_mod.anthropic, "Anthropic", lambda: "anthropic-client")
    monkeypatch.setattr(main_mod.orchestrator, "validate_board_config", lambda client: None)


def _run_log(tmp_path):
    return json.loads((tmp_path / "runlog.json").read_text())


def test_dry_run_comments_but_does_not_mutate(monkeypatch, tmp_path):
    _base_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result(kwargs["run_id"]))

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
    _base_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result(kwargs["run_id"]))
    monkeypatch.setattr(main_mod, "post_comment", lambda *a, **k: None)
    mutated = {"called": False}
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: mutated.__setitem__("called", True))

    monkeypatch.setattr(sys, "argv", ["main", "--no-dry-run"])
    main_mod.main()

    assert mutated["called"] is True


def test_posts_slack_summary_when_webhook_configured_and_something_changed(monkeypatch, tmp_path):
    _base_setup(monkeypatch, tmp_path)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result(kwargs["run_id"]))
    monkeypatch.setattr(main_mod, "post_comment", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: None)

    posted = {}
    monkeypatch.setattr(main_mod, "post_summary", lambda url, text: posted.update(url=url, text=text))

    monkeypatch.setattr(sys, "argv", ["main"])
    main_mod.main()

    assert posted["url"] == "https://hooks.slack.test/x"
    assert "#1" in posted["text"]


def test_no_slack_post_without_a_webhook_url(monkeypatch, tmp_path):
    _base_setup(monkeypatch, tmp_path)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result(kwargs["run_id"]))
    monkeypatch.setattr(main_mod, "post_comment", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: None)

    called = {"n": 0}
    monkeypatch.setattr(main_mod, "post_summary", lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    monkeypatch.setattr(sys, "argv", ["main"])
    main_mod.main()

    assert called["n"] == 0


def test_dry_run_does_not_persist_this_runs_evidence_hash(monkeypatch, tmp_path):
    """A dry run writes nothing for real - if its run-log entry were
    persisted anyway, a later --no-dry-run run would see "unchanged
    evidence" and silently skip the real transition.
    """
    _base_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result(kwargs["run_id"]))
    monkeypatch.setattr(main_mod, "post_comment", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: None)

    monkeypatch.setattr(sys, "argv", ["main"])
    main_mod.main()

    assert _run_log(tmp_path) == []


def test_no_dry_run_persists_this_runs_evidence_hash(monkeypatch, tmp_path):
    _base_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result(kwargs["run_id"]))
    monkeypatch.setattr(main_mod, "post_comment", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: None)

    monkeypatch.setattr(sys, "argv", ["main", "--no-dry-run"])
    main_mod.main()

    log = _run_log(tmp_path)
    assert len(log) == 1
    assert log[0]["issue_number"] == 1


def test_circuit_broken_run_skips_writes_and_does_not_persist_the_entry(monkeypatch, tmp_path):
    """The plan requires a circuit-broken run to stop writing entirely, not
    just report a failing exit code - a decision reached before the breaker
    tripped was never actually posted/mutated.
    """
    _base_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result(kwargs["run_id"], circuit_broken=True))
    commented = {"called": False}
    monkeypatch.setattr(main_mod, "post_comment", lambda *a, **k: commented.__setitem__("called", True))
    mutated = {"called": False}
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: mutated.__setitem__("called", True))

    monkeypatch.setattr(sys, "argv", ["main", "--no-dry-run"])
    exit_code = main_mod.main()

    assert exit_code == 1
    assert commented["called"] is False
    assert mutated["called"] is False
    assert _run_log(tmp_path) == []


def test_a_failed_write_is_excluded_from_the_persisted_run_log(monkeypatch, tmp_path):
    """One issue's comment/mutate failure must not be recorded as "seen" -
    otherwise the next run's unchanged-evidence check wrongly skips retrying
    a transition that never actually happened.
    """
    _base_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(main_mod.orchestrator, "run", lambda **kwargs: _fake_result(kwargs["run_id"]))

    def failing_post_comment(*_a, **_k):
        raise RuntimeError("network error")

    monkeypatch.setattr(main_mod, "post_comment", failing_post_comment)
    monkeypatch.setattr(main_mod, "mutate", lambda *a, **k: None)

    monkeypatch.setattr(sys, "argv", ["main", "--no-dry-run"])
    exit_code = main_mod.main()  # must not crash - one issue's failure isn't fatal to the run

    assert exit_code == 0
    assert _run_log(tmp_path) == []
