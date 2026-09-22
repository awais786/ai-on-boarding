from __future__ import annotations

import pytest
from claude_agent_sdk import AssistantMessage, TextBlock

from mautic_sso_discovery.discover import build_system_prompt, build_task_prompt, run_discover


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


def test_run_discover_raises_on_empty_final_report(tmp_path):
    async def empty_query(*, prompt, options):
        yield AssistantMessage(content=[TextBlock(text="")], model="test")

    with pytest.raises(RuntimeError, match="no final report"):
        run_discover(
            "https://example.com/repo",
            tmp_path / "report.md",
            tmp_path,
            query_impl=empty_query,
            clone_impl=lambda url, dest: dest.mkdir(parents=True),
            lock_down_impl=lambda path: None,
        )
