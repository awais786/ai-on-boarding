"""Phase 1 (`discover`): explores an already-cloned, already-locked-down
target repo with a Claude Agent SDK session and writes a Markdown
discovery report + SSO integration plan. The session has no Write/Edit/Bash
tool - Read/Grep/Glob only - so even if the write-lockdown in cloning.py
were somehow bypassed, the model still has no tool capable of writing to
the checkout. The report itself is written by this module's own code from
the session's final text, not by a tool call the model makes.
"""
from __future__ import annotations

import functools
from pathlib import Path

import anyio
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from mautic_sso_discovery.cloning import clone_repo, lock_down
from mautic_sso_discovery.context import load_moneta_contract

_REQUIRED_TASK_SECTIONS = [
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
]


def build_system_prompt() -> str:
    return (
        "You are a security-and-architecture discovery agent. You are auditing "
        "a target codebase's current authentication implementation against a "
        "fixed SSO contract (given below) that the target app must eventually "
        "satisfy.\n\n"
        "Rules:\n"
        "- Every non-trivial claim about the target codebase MUST cite an exact "
        "file path and line number/range from the checkout at your current "
        "working directory.\n"
        "- Anything you cannot verify by reading the code MUST be labeled "
        "`ASSUMPTION` or `UNKNOWN` - never stated as fact.\n"
        "- You must not attempt to modify the target checkout. You have no "
        "Write/Edit/Bash tools; only Read, Grep, and Glob.\n"
        "- Do all exploration first. Your FINAL message must contain nothing "
        "but the complete Markdown report, and nothing else - no preamble, no "
        "'here is the report'.\n\n"
        "The fixed SSO contract you are comparing against:\n\n"
        f"{load_moneta_contract()}"
    )


def build_task_prompt(target_repo_url: str) -> str:
    numbered = "\n".join(f"{i + 1}. {section}" for i, section in enumerate(_REQUIRED_TASK_SECTIONS))
    return (
        f"The target repository ({target_repo_url}) is checked out read-only at "
        "your current working directory. Investigate it and write a Markdown "
        f"report with exactly these sections, in this order:\n\n{numbered}\n\n"
        "For sections 1-8, trace the real code (using Read/Grep/Glob) rather "
        "than assuming based on framework conventions. Section 9 (Gap "
        "analysis) must explicitly compare sections 1-8 against the fixed SSO "
        "contract above. Section 10 must propose a concrete SSO integration "
        "architecture (auth flow, claims/identity mapping, user/role "
        "provisioning, logout, session handling, security considerations). "
        "Section 11 must be actionable and reference concrete files."
    )


async def _collect_final_report_text(prompt: str, options: ClaudeAgentOptions, *, query_impl) -> str:
    last_text = ""
    async for message in query_impl(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            text = "".join(block.text for block in message.content if isinstance(block, TextBlock))
            if text:
                last_text = text
    return last_text


def run_discover(
    target_repo_url: str,
    out_path: Path,
    workdir: Path,
    *,
    query_impl=query,
    clone_impl=clone_repo,
    lock_down_impl=lock_down,
) -> None:
    clone_dir = workdir / "target-repo"
    clone_impl(target_repo_url, clone_dir)
    lock_down_impl(clone_dir)

    options = ClaudeAgentOptions(
        system_prompt=build_system_prompt(),
        cwd=clone_dir,
        allowed_tools=["Read", "Grep", "Glob"],
        disallowed_tools=["Bash", "Write", "Edit", "NotebookEdit"],
        permission_mode="bypassPermissions",
        max_turns=60,
        model="claude-sonnet-5",
    )

    report = anyio.run(
        functools.partial(
            _collect_final_report_text,
            build_task_prompt(target_repo_url),
            options,
            query_impl=query_impl,
        )
    )

    if not report.strip():
        raise RuntimeError("discovery agent produced no final report text")

    out_path.write_text(report)
