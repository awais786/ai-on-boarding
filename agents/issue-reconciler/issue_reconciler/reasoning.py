"""Four AI reasoning spokes - each answers one judgment call a lookup can't.
Only called for an issue that already has a linked PR (a model call is
never how the pipeline finds work in the first place, only how it double-
checks work it already found). A spoke that can't produce a clean verdict
returns None rather than guessing or raising - see rules.py's
apply_verdicts: a verdict can only ever demote a decision to a human flag,
never confirm or upgrade one, so "no opinion" is always a safe default.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import TypedDict

import anthropic

from issue_reconciler.prompts import (
    build_activity_prompt,
    build_completion_prompt,
    build_reference_prompt,
    build_stale_prompt,
)
from issue_reconciler.types import LinkedPR

MODEL = "claude-haiku-4-5"
MAX_ATTEMPTS = 2


def _ask(client: anthropic.Anthropic, prompt: str, schema: dict, required_keys: set[str]) -> dict | None:
    """A genuine anthropic.APIError propagates for the orchestrator's own
    handling. Only a malformed response body is retried, then treated as
    "no verdict" - same shape as the old fuzzy matcher's retry contract.
    """
    for _attempt in range(MAX_ATTEMPTS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
            # temperature isn't a top-level SDK param on this anthropic
            # version - extra_body forwards it to the raw API. A verdict,
            # not prose: minimize run-to-run flip-flopping on borderline cases.
            extra_body={"temperature": 0},
        )
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and required_keys <= parsed.keys():
            return parsed
    return None


class CompletionVerdict(TypedDict):
    fully_resolved: bool
    reasoning: str


_COMPLETION_SCHEMA = {
    "type": "object",
    "properties": {"fully_resolved": {"type": "boolean"}, "reasoning": {"type": "string"}},
    "required": ["fully_resolved", "reasoning"],
    "additionalProperties": False,
}


def completion_check(client: anthropic.Anthropic, issue_title: str, linked_prs: list[LinkedPR]) -> CompletionVerdict | None:
    """Do the linked PRs, together, fully resolve the issue - or only
    partially (e.g. one of several needed changes)?
    """
    return _ask(client, build_completion_prompt(issue_title, linked_prs), _COMPLETION_SCHEMA, {"fully_resolved", "reasoning"})


class ActivityVerdict(TypedDict):
    status: str  # "active" | "blocked" | "abandoned"
    reasoning: str


_ACTIVITY_SCHEMA = {
    "type": "object",
    "properties": {"status": {"type": "string", "enum": ["active", "blocked", "abandoned"]}, "reasoning": {"type": "string"}},
    "required": ["status", "reasoning"],
    "additionalProperties": False,
}


def activity_check(client: anthropic.Anthropic, issue_title: str, pr: LinkedPR, now: datetime) -> ActivityVerdict | None:
    """Is this open, linked PR still active, blocked, or abandoned?"""
    return _ask(client, build_activity_prompt(issue_title, pr, now), _ACTIVITY_SCHEMA, {"status", "reasoning"})


class ReferenceVerdict(TypedDict):
    matches: bool
    reasoning: str


_REFERENCE_SCHEMA = {
    "type": "object",
    "properties": {"matches": {"type": "boolean"}, "reasoning": {"type": "string"}},
    "required": ["matches", "reasoning"],
    "additionalProperties": False,
}


def reference_validation(client: anthropic.Anthropic, issue_title: str, pr: LinkedPR) -> ReferenceVerdict | None:
    """Does the PR's reference actually match this issue's intent, or does
    it look like a wrong/copy-pasted issue number?
    """
    return _ask(client, build_reference_prompt(issue_title, pr), _REFERENCE_SCHEMA, {"matches", "reasoning"})


class StaleVerdict(TypedDict):
    superseded: bool
    reasoning: str


_STALE_SCHEMA = {
    "type": "object",
    "properties": {"superseded": {"type": "boolean"}, "reasoning": {"type": "string"}},
    "required": ["superseded", "reasoning"],
    "additionalProperties": False,
}


def stale_or_superseded_check(client: anthropic.Anthropic, issue_title: str, linked_prs: list[LinkedPR]) -> StaleVerdict | None:
    """Has an earlier linked PR been superseded by a later one solving the
    problem differently, rather than building on it? Only meaningful with
    more than one linked PR.
    """
    return _ask(client, build_stale_prompt(issue_title, linked_prs), _STALE_SCHEMA, {"superseded", "reasoning"})
