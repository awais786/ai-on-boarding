from __future__ import annotations

import anyio
import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from mautic_sso_discovery.discover import (
    _search_before_read_hooks,
    build_system_prompt,
    build_task_prompt,
    run_discover,
)


def _result(**overrides) -> ResultMessage:
    """A ResultMessage for a normally-completed session, with the
    required fields filled in and everything else defaulted - override
    only what a given test cares about (e.g. is_error, terminal_reason).
    """
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


def test_build_system_prompt_includes_contract_and_tool_rules():
    prompt = build_system_prompt()
    assert "Source: authentication.md" in prompt
    assert "ASSUMPTION" in prompt
    assert "UNKNOWN" in prompt
    assert "Write/Edit/Bash" in prompt


def test_build_task_prompt_lists_all_required_sections():
    prompt = build_task_prompt("https://example.com/repo")
    for heading in [
        "Authentication today",
        "Login flow",
        "Logout flow",
        "Users",
        "Sessions",
        "Roles/permissions/RBAC",
        "Existing OAuth/OIDC",
        "Extension points",
        "Gap analysis",
        "Proposed SSO integration architecture",
        "Implementation and test plan",
    ]:
        assert heading in prompt


async def _fake_query(*, prompt, options):
    yield AssistantMessage(content=[TextBlock(text="exploring the repo...")], model="test")
    yield AssistantMessage(content=[TextBlock(text="# Discovery Report\n\nfinal content")], model="test")
    yield _result()


def test_run_discover_clones_locks_down_and_writes_final_report_text(tmp_path):
    calls = {}

    def fake_clone(url, dest):
        calls["cloned"] = (url, dest)
        dest.mkdir(parents=True)

    def fake_lock_down(path):
        calls["locked"] = path

    out_path = tmp_path / "report.md"

    run_discover(
        "https://example.com/repo",
        out_path,
        tmp_path,
        query_impl=_fake_query,
        clone_impl=fake_clone,
        lock_down_impl=fake_lock_down,
    )

    assert out_path.read_text() == "# Discovery Report\n\nfinal content"
    assert calls["cloned"] == ("https://example.com/repo", tmp_path / "target-repo")
    assert calls["locked"] == tmp_path / "target-repo"


def test_run_discover_creates_missing_out_dir(tmp_path):
    out_path = tmp_path / "missing" / "nested" / "report.md"

    run_discover(
        "https://example.com/repo",
        out_path,
        tmp_path,
        query_impl=_fake_query,
        clone_impl=lambda url, dest: dest.mkdir(parents=True),
        lock_down_impl=lambda path: None,
    )

    assert out_path.read_text() == "# Discovery Report\n\nfinal content"


def _hook(hooks: dict, tool_name: str):
    """Pulls the single callback registered for `tool_name` out of the
    hooks dict returned by _search_before_read_hooks() (Grep/Glob are
    under PostToolUse, Read is under PreToolUse), so the tests below can
    invoke it directly without a real SDK session.
    """
    for matchers in hooks.values():
        for matcher in matchers:
            if matcher.matcher == tool_name:
                return matcher.hooks[0]
    raise AssertionError(f"no hook registered for {tool_name!r}")


def test_search_before_read_hooks_denies_read_before_any_search():
    hooks = _search_before_read_hooks()
    read_hook = _hook(hooks, "Read")

    result = anyio.run(read_hook, {}, "tool-use-id", {})

    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_search_before_read_hooks_allows_read_after_a_grep():
    hooks = _search_before_read_hooks()
    grep_hook = _hook(hooks, "Grep")
    read_hook = _hook(hooks, "Read")

    anyio.run(grep_hook, {}, "tool-use-id", {})
    result = anyio.run(read_hook, {}, "tool-use-id", {})

    assert result == {}


def test_search_before_read_hooks_allows_read_after_a_glob():
    hooks = _search_before_read_hooks()
    glob_hook = _hook(hooks, "Glob")
    read_hook = _hook(hooks, "Read")

    anyio.run(glob_hook, {}, "tool-use-id", {})
    result = anyio.run(read_hook, {}, "tool-use-id", {})

    assert result == {}


def test_search_before_read_hooks_state_is_independent_per_call():
    first_run_hooks = _search_before_read_hooks()
    anyio.run(_hook(first_run_hooks, "Grep"), {}, "tool-use-id", {})

    second_run_hooks = _search_before_read_hooks()
    result = anyio.run(_hook(second_run_hooks, "Read"), {}, "tool-use-id", {})

    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_run_discover_builds_options_with_hardened_tool_and_settings_restrictions(tmp_path):
    captured = {}

    async def capturing_query(*, prompt, options):
        captured["options"] = options
        yield AssistantMessage(content=[TextBlock(text="report")], model="test")
        yield _result()

    run_discover(
        "https://example.com/repo",
        tmp_path / "report.md",
        tmp_path,
        query_impl=capturing_query,
        clone_impl=lambda url, dest: dest.mkdir(parents=True),
        lock_down_impl=lambda path: None,
    )

    options = captured["options"]
    assert options.tools == ["Read", "Grep", "Glob"]
    assert options.setting_sources == []
    assert {matcher.matcher for matcher in options.hooks["PreToolUse"]} == {"Read"}
    assert {matcher.matcher for matcher in options.hooks["PostToolUse"]} == {"Grep", "Glob"}


def test_run_discover_raises_on_empty_final_report(tmp_path):
    async def empty_query(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text="")], model="test")
        yield _result()

    with pytest.raises(RuntimeError, match="no final report"):
        run_discover(
            "https://example.com/repo",
            tmp_path / "report.md",
            tmp_path,
            query_impl=empty_query,
            clone_impl=lambda url, dest: dest.mkdir(parents=True),
            lock_down_impl=lambda path: None,
        )


def test_run_discover_raises_on_max_turns_truncation(tmp_path):
    async def truncated_query(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text="still exploring, ran out of turns")], model="test")
        yield _result(is_error=False, terminal_reason="max_turns")

    with pytest.raises(RuntimeError, match="max_turns"):
        run_discover(
            "https://example.com/repo",
            tmp_path / "report.md",
            tmp_path,
            query_impl=truncated_query,
            clone_impl=lambda url, dest: dest.mkdir(parents=True),
            lock_down_impl=lambda path: None,
        )


def test_run_discover_raises_on_session_error(tmp_path):
    async def erroring_query(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text="# Discovery Report\n\nlooks done but isn't")], model="test")
        yield _result(is_error=True, subtype="error_during_execution")

    with pytest.raises(RuntimeError, match="error"):
        run_discover(
            "https://example.com/repo",
            tmp_path / "report.md",
            tmp_path,
            query_impl=erroring_query,
            clone_impl=lambda url, dest: dest.mkdir(parents=True),
            lock_down_impl=lambda path: None,
        )
