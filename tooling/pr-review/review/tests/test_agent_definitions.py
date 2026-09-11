"""Tests for the .claude/agents/*.md subagent definitions, written from the pr-review
spec's "Select only relevant review skills" and design.md's Decisions 1-3: each skill
is a subagent with its own pinned model, restricted to Read+Skill only (so it cannot
post to GitHub itself), referencing skills that actually exist on disk.

This is a repo-structure check, not a review.* package test - it makes this
implicit contract explicit and catches a future edit that silently breaks it (e.g.
a typo'd model name, an accidentally widened tool list, a renamed skill directory).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

EXPECTED = {
    "security-review.md": ("opus", "security-review-checklist"),
    "architecture-review.md": ("opus", "architecture-review-checklist"),
    "optimization.md": ("sonnet", "optimization-checklist"),
    "code-quality.md": ("haiku", "code-quality-checklist"),
}


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    assert text.startswith("---\n"), "missing opening frontmatter delimiter"
    end = text.index("\n---\n", 4)
    frontmatter = text[4:end]
    body = text[end + 5 :]
    fields = dict(re.findall(r"^(\w+):\s*(.+)$", frontmatter, re.MULTILINE))
    return fields, body


def test_all_four_expected_agent_files_exist():
    for filename in EXPECTED:
        assert (AGENTS_DIR / filename).is_file(), f"{filename} is missing"


def test_pr_review_common_skill_exists():
    assert (SKILLS_DIR / "pr-review-common" / "SKILL.md").is_file()


def test_each_agent_has_its_pinned_model():
    for filename, (expected_model, _checklist) in EXPECTED.items():
        fields, _ = _parse_frontmatter((AGENTS_DIR / filename).read_text())
        assert fields.get("model") == expected_model, (
            f"{filename}: model is {fields.get('model')!r}, expected {expected_model!r}"
        )


def test_each_agent_is_restricted_to_read_and_skill_only():
    for filename in EXPECTED:
        fields, _ = _parse_frontmatter((AGENTS_DIR / filename).read_text())
        tools = {t.strip() for t in fields.get("tools", "").split(",")}
        assert tools == {"Read", "Skill"}, (
            f"{filename}: tools are {tools}, expected exactly Read and Skill - a wider "
            "tool list would let this subagent post to GitHub itself"
        )


def test_each_agent_references_pr_review_common_and_its_own_checklist():
    for filename, (_model, checklist) in EXPECTED.items():
        _, body = _parse_frontmatter((AGENTS_DIR / filename).read_text())
        assert "pr-review-common" in body, f"{filename}: does not reference pr-review-common"
        assert checklist in body, f"{filename}: does not reference {checklist}"


def test_every_referenced_checklist_skill_exists_on_disk():
    for _filename, (_model, checklist) in EXPECTED.items():
        assert (SKILLS_DIR / checklist / "SKILL.md").is_file(), (
            f"referenced skill {checklist!r} does not exist"
        )
