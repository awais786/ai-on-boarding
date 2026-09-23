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
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, query

from mautic_sso_discovery.cloning import clone_repo, lock_down
from mautic_sso_discovery.context import load_moneta_contract
from mautic_sso_discovery.sdk_session import collect_final_text

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
        "Method:\n"
        "- Before concluding something doesn't exist (an SSO mechanism, a "
        "config file, an entity field), search for it under multiple "
        "plausible names (e.g. auth, login, session, sso, oauth, saml, "
        "security) - a single grep miss is not evidence of absence.\n"
        "- Check the project's dependency manifest (composer.json, "
        "package.json, requirements.txt, go.mod, or whatever this "
        "ecosystem uses) for already-installed auth/SSO/OAuth-related "
        "packages before assuming none exist.\n"
        "- Verify every citation by opening the file and reading enough "
        "surrounding context to confirm what it actually does - a keyword "
        "match alone is not a citation.\n"
        "- Budget your exploration across all required sections; don't "
        "exhaust your turns going deep on the first one and leave later "
        "sections thin or unverified.\n"
        "- Use Grep/Glob to locate candidate files by keyword before "
        "reading anything. Read only the files that turn out relevant to "
        "authentication, users, sessions, roles/permissions, or OAuth/OIDC "
        "- do not read a file just because it exists. A large codebase has "
        "many files with nothing to do with auth; opening them wastes your "
        "turn budget and adds nothing to the report.\n\n"
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


def _search_before_read_hooks() -> dict:
    """Enforces "search before read" in code, not just in the prompt: a
    fresh Read is denied until at least one Grep or Glob call has actually
    succeeded in this session. The system prompt already asks for this,
    but a prompt is a request the model can ignore under pressure; this
    hook makes it the actual rule. State is a plain dict closed over by
    both callbacks - fresh per call, so two discovery runs never share it.

    _mark_searched is registered on PostToolUse, not PreToolUse: a
    PreToolUse hook fires before the tool call runs, so it would flip
    `searched` even if that Grep/Glob was itself denied or errored.
    PostToolUse only fires once the call actually succeeded (a distinct
    PostToolUseFailure event covers the failure case) - so a Read can
    only unlock once a search has genuinely completed.
    """
    state = {"searched": False}

    async def _mark_searched(input_data, tool_use_id, context):
        state["searched"] = True
        return {}

    async def _require_search_first(input_data, tool_use_id, context):
        if state["searched"]:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Use Grep or Glob to locate a candidate file before reading it.",
            }
        }

    return {
        "PostToolUse": [
            HookMatcher(matcher="Grep", hooks=[_mark_searched]),
            HookMatcher(matcher="Glob", hooks=[_mark_searched]),
        ],
        "PreToolUse": [
            HookMatcher(matcher="Read", hooks=[_require_search_first]),
        ]
    }


def run_discover(
    target_repo_url: str,
    out_path: Path,
    workdir: Path,
    *,
    model: str = "claude-sonnet-5",
    query_impl=query,
    clone_impl=clone_repo,
    lock_down_impl=lock_down,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    clone_dir = workdir / "target-repo"
    clone_impl(target_repo_url, clone_dir)
    lock_down_impl(clone_dir)

    options = ClaudeAgentOptions(
        system_prompt=build_system_prompt(),
        cwd=clone_dir,
        # `tools` is a real restriction on which built-in tools even exist
        # for this session (confirmed against claude_agent_sdk>=0.2.x's own
        # docstring: "Specify the base set of available built-in tools").
        # This closes everything not named here - Bash, Write, Edit,
        # WebFetch, WebSearch, etc - rather than a hand-maintained denylist
        # that has to be kept in sync with every tool the SDK ever adds.
        tools=["Read", "Grep", "Glob"],
        # Don't inherit MCP servers or other config from the operator's own
        # user/project/local Claude settings.
        setting_sources=[],
        permission_mode="bypassPermissions",
        max_turns=60,
        model=model,
        # Code-enforced version of the system prompt's "search before you
        # read" instruction - a Read call is denied until Grep/Glob has
        # run at least once in this session.
        hooks=_search_before_read_hooks(),
    )

    report = anyio.run(
        functools.partial(
            collect_final_text,
            build_task_prompt(target_repo_url),
            options,
            query_impl=query_impl,
        )
    )

    if not report.strip():
        raise RuntimeError("discovery agent produced no final report text")

    out_path.write_text(report)
