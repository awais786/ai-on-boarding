from __future__ import annotations

import json

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
from support import make_sequential_client

from mautic_sso_discovery.propose_issues import (
    build_propose_prompt,
    create_issues,
    parse_issue_drafts,
    run_propose_issues,
)


def _result(**overrides) -> ResultMessage:
    defaults = dict(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="test-session",
        terminal_reason="completed",
    )
    return ResultMessage(**{**defaults, **overrides})


def test_run_propose_issues_rejects_malformed_github_repo(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report")

    with pytest.raises(ValueError, match="owner/name"):
        run_propose_issues(report_path, "not-a-valid-repo", client=None)


def test_build_propose_prompt_requires_json_only_response_and_embeds_report():
    prompt = build_propose_prompt("some report text")
    assert "ONLY a JSON array" in prompt
    assert "some report text" in prompt


def test_build_propose_prompt_constrains_granularity():
    prompt = build_propose_prompt("some report text")
    assert "One issue per core code change" in prompt
    assert "Fold that change's own tests into its own issue" in prompt
    assert "Do NOT create separate issues for documentation" in prompt


def test_parse_issue_drafts_accepts_valid_array():
    raw = json.dumps(
        [
            {"title": "A", "body": "body a", "depends_on": []},
            {"title": "B", "body": "body b", "depends_on": ["A"]},
        ]
    )
    drafts = parse_issue_drafts(raw)
    assert [d["title"] for d in drafts] == ["A", "B"]


def test_parse_issue_drafts_rejects_unknown_dependency():
    raw = json.dumps([{"title": "A", "body": "x", "depends_on": ["Ghost"]}])
    with pytest.raises(ValueError, match="Ghost"):
        parse_issue_drafts(raw)


def test_parse_issue_drafts_rejects_duplicate_titles():
    raw = json.dumps(
        [
            {"title": "A", "body": "first", "depends_on": []},
            {"title": "A", "body": "second", "depends_on": []},
        ]
    )
    with pytest.raises(ValueError, match="duplicate"):
        parse_issue_drafts(raw)


def test_create_issues_creates_in_dependency_order_and_links_urls():
    client, calls = make_sequential_client(
        [
            {"repository": {"id": "REPO_ID"}},
            {"createIssue": {"issue": {"number": 1, "url": "https://github.com/x/y/issues/1"}}},
            {"createIssue": {"issue": {"number": 2, "url": "https://github.com/x/y/issues/2"}}},
        ]
    )
    drafts = [
        {"title": "A", "body": "body a", "depends_on": []},
        {"title": "B", "body": "body b", "depends_on": ["A"]},
    ]

    urls = create_issues(client, "x", "y", drafts)

    assert urls == {"A": "https://github.com/x/y/issues/1", "B": "https://github.com/x/y/issues/2"}
    assert "https://github.com/x/y/issues/1" in calls[2]["variables"]["body"]


def test_create_issues_applies_title_prefix_but_keeps_original_titles_as_dict_keys():
    client, calls = make_sequential_client(
        [
            {"repository": {"id": "REPO_ID"}},
            {"createIssue": {"issue": {"number": 1, "url": "https://github.com/x/y/issues/1"}}},
        ]
    )
    drafts = [{"title": "A", "body": "body a", "depends_on": []}]

    urls = create_issues(client, "x", "y", drafts, title_prefix="[TEST] ")

    assert calls[1]["variables"]["title"] == "[TEST] A"
    assert urls == {"A": "https://github.com/x/y/issues/1"}


def test_create_issues_raises_on_circular_dependency():
    client, _ = make_sequential_client([{"repository": {"id": "REPO_ID"}}])
    drafts = [
        {"title": "A", "body": "x", "depends_on": ["B"]},
        {"title": "B", "body": "y", "depends_on": ["A"]},
    ]
    with pytest.raises(ValueError, match="circular"):
        create_issues(client, "x", "y", drafts)


def test_run_propose_issues_end_to_end(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n\n## Implementation and test plan\n...")

    async def fake_query(*, prompt, options):
        yield AssistantMessage(
            content=[TextBlock(text=json.dumps([{"title": "A", "body": "b", "depends_on": []}]))],
            model="test",
        )
        yield _result()

    client, _ = make_sequential_client(
        [
            {"repository": {"id": "REPO_ID"}},
            {"createIssue": {"issue": {"number": 1, "url": "https://github.com/x/y/issues/1"}}},
        ]
    )

    urls = run_propose_issues(report_path, "x/y", client, query_impl=fake_query)

    assert urls == {"A": "https://github.com/x/y/issues/1"}


def test_run_propose_issues_builds_options_with_hardened_tool_and_settings_restrictions(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n\n## Implementation and test plan\n...")
    captured = {}

    async def capturing_query(*, prompt, options):
        captured["options"] = options
        yield AssistantMessage(
            content=[TextBlock(text=json.dumps([{"title": "A", "body": "b", "depends_on": []}]))],
            model="test",
        )
        yield _result()

    client, _ = make_sequential_client(
        [
            {"repository": {"id": "REPO_ID"}},
            {"createIssue": {"issue": {"number": 1, "url": "https://github.com/x/y/issues/1"}}},
        ]
    )

    run_propose_issues(report_path, "x/y", client, query_impl=capturing_query)

    options = captured["options"]
    assert options.tools == []
    assert options.setting_sources == []


def test_run_propose_issues_passes_through_custom_model(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n\n## Implementation and test plan\n...")
    captured = {}

    async def capturing_query(*, prompt, options):
        captured["options"] = options
        yield AssistantMessage(
            content=[TextBlock(text=json.dumps([{"title": "A", "body": "b", "depends_on": []}]))],
            model="test",
        )
        yield _result()

    client, _ = make_sequential_client(
        [
            {"repository": {"id": "REPO_ID"}},
            {"createIssue": {"issue": {"number": 1, "url": "https://github.com/x/y/issues/1"}}},
        ]
    )

    run_propose_issues(report_path, "x/y", client, model="claude-haiku-4-5-20251001", query_impl=capturing_query)

    assert captured["options"].model == "claude-haiku-4-5-20251001"


def test_run_propose_issues_raises_on_truncated_session_before_creating_anything(tmp_path):
    """A truncated draft either fails to parse, or - worse - parses into a
    partial issue list that would then get created for real on GitHub.
    Neither should happen: a truncated session must fail before create_issues
    is ever called.
    """
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n\n## Implementation and test plan\n...")

    async def truncated_query(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text='[{"title": "A", "body": "b"')], model="test")
        yield _result(terminal_reason="max_turns")

    client, calls = make_sequential_client([{"repository": {"id": "REPO_ID"}}])

    with pytest.raises(RuntimeError, match="max_turns"):
        run_propose_issues(report_path, "x/y", client, query_impl=truncated_query)

    assert calls == []


def test_run_propose_issues_raises_on_session_error_before_creating_anything(tmp_path):
    report_path = tmp_path / "report.md"
    report_path.write_text("# Report\n\n## Implementation and test plan\n...")

    async def erroring_query(*, prompt, options):
        yield AssistantMessage(
            content=[TextBlock(text=json.dumps([{"title": "A", "body": "b", "depends_on": []}]))],
            model="test",
        )
        yield _result(is_error=True, subtype="error_during_execution")

    client, calls = make_sequential_client([{"repository": {"id": "REPO_ID"}}])

    with pytest.raises(RuntimeError, match="error"):
        run_propose_issues(report_path, "x/y", client, query_impl=erroring_query)

    assert calls == []
