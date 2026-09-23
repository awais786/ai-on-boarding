"""Phase 2 (`propose-issues`): a separate, human-gated invocation. Drafting
(what issues to create) is the model's job; creating them is plain code
that uses this package's own GitHubClient, so a bad draft is a JSON value
to review, not a live API call to debug. The report text is pasted
directly into the prompt rather than read via a tool, so this session
needs zero tools at all - simpler and strictly safer than granting a
scoped Read tool for one file.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import TypedDict

import anyio
from claude_agent_sdk import ClaudeAgentOptions, query

from mautic_sso_discovery.github_client import GitHubClient
from mautic_sso_discovery.sdk_session import collect_final_text

_REPO_ID_QUERY = "query RepoId($owner: String!, $name: String!) { repository(owner: $owner, name: $name) { id } }"
_CREATE_ISSUE = (
    "mutation CreateIssue($repositoryId: ID!, $title: String!, $body: String!) "
    "{ createIssue(input: { repositoryId: $repositoryId, title: $title, body: $body }) "
    "{ issue { number url } } }"
)


class IssueDraft(TypedDict):
    title: str
    body: str
    depends_on: list[str]


def build_propose_prompt(report_text: str) -> str:
    return (
        "Below is a completed SSO discovery report for a target codebase. "
        "Break its 'Implementation and test plan' section into small, "
        "independently scoped GitHub issues. Each issue must be small enough "
        "to review in one pull request.\n\n"
        "Respond with ONLY a JSON array (no prose, no code fences) where each "
        "element has exactly these keys:\n"
        '- "title": short imperative summary\n'
        '- "body": Markdown body including Scope, Affected files, Acceptance '
        "criteria, and Tests sections, each referencing concrete files named "
        "in the report\n"
        '- "depends_on": a list of the exact "title" strings of other issues '
        "in this same array that must land first, or an empty list\n\n"
        f"--- REPORT ---\n{report_text}"
    )


def parse_issue_drafts(raw_json: str) -> list[IssueDraft]:
    drafts = json.loads(raw_json)
    if not isinstance(drafts, list):
        raise ValueError("expected a JSON array of issue drafts")
    titles = {d["title"] for d in drafts}
    for draft in drafts:
        unknown = set(draft.get("depends_on", [])) - titles
        if unknown:
            raise ValueError(f"issue {draft['title']!r} depends on unknown title(s): {unknown}")
    return drafts


def create_issues(client: GitHubClient, owner: str, name: str, drafts: list[IssueDraft]) -> dict[str, str]:
    """Creates each issue in dependency order (a draft with no unmet
    dependency first), appending a note of already-created dependency URLs
    into the body, since GitHub issues can't cross-link to a dependency
    that doesn't exist yet at draft time. Returns {title: issue_url}.
    """
    repository_id = client.query(_REPO_ID_QUERY, {"owner": owner, "name": name})["repository"]["id"]

    remaining = list(drafts)
    created_urls: dict[str, str] = {}
    while remaining:
        ready = [d for d in remaining if all(dep in created_urls for dep in d.get("depends_on", []))]
        if not ready:
            raise ValueError("circular dependency among issue drafts")
        for draft in ready:
            body = draft["body"]
            if draft.get("depends_on"):
                deps_line = ", ".join(f"{created_urls[dep]} ({dep})" for dep in draft["depends_on"])
                body = f"{body}\n\n---\nDepends on: {deps_line}"
            result = client.query(
                _CREATE_ISSUE,
                {"repositoryId": repository_id, "title": draft["title"], "body": body},
            )
            created_urls[draft["title"]] = result["createIssue"]["issue"]["url"]
            remaining.remove(draft)
    return created_urls


def draft_issues(
    report_path: Path,
    *,
    model: str = "claude-sonnet-5",
    query_impl=query,
) -> list[IssueDraft]:
    """Just the drafting half: asks the model to break the report into
    issues and parses its answer. Doesn't touch GitHub at all - split out
    so a --dry-run can preview drafts without needing a GitHubClient or
    BOARD_TOKEN, and without any risk of a bad draft actually creating
    anything.
    """
    report_text = report_path.read_text()

    options = ClaudeAgentOptions(
        # No tools at all - the report text is pasted directly into the
        # prompt, so this session has nothing on disk or on GitHub it
        # needs to reach. `tools=[]` is a real restriction (confirmed
        # against claude_agent_sdk>=0.2.x's own docstring: "[] (empty
        # list) - Disable all built-in tools"), not an advisory list.
        tools=[],
        # Don't inherit MCP servers or other config from the operator's own
        # user/project/local Claude settings.
        setting_sources=[],
        permission_mode="bypassPermissions",
        max_turns=5,
        model=model,
    )

    raw = anyio.run(
        functools.partial(
            collect_final_text,
            build_propose_prompt(report_text),
            options,
            query_impl=query_impl,
        )
    )
    return parse_issue_drafts(raw)


def run_propose_issues(
    report_path: Path,
    github_repo: str,
    client: GitHubClient,
    *,
    model: str = "claude-sonnet-5",
    query_impl=query,
) -> dict[str, str]:
    if github_repo.count("/") != 1:
        raise ValueError(f"--github-repo must be 'owner/name', got {github_repo!r}")
    owner, name = github_repo.split("/", 1)

    drafts = draft_issues(report_path, model=model, query_impl=query_impl)
    return create_issues(client, owner, name, drafts)
