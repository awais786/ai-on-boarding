"""The only model call in the system. Never called when an explicit PR
reference exists - see plan hard constraint #1: the model never touches the
GitHub API, only normalized JSON in, a verdict out.
"""
from __future__ import annotations

import json
from typing import Any, TypedDict

import anthropic

# Haiku per plan: this is a narrow title/branch-similarity judgment, not a
# task that needs a frontier model.
MODEL = "claude-haiku-4-5"
MAX_ATTEMPTS = 2

_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "pr_number": {"type": "integer"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["pr_number", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["matches"],
        "additionalProperties": False,
    },
}


class FuzzyCandidate(TypedDict):
    number: int
    title: str
    head_ref_name: str


class FuzzyMatch(TypedDict):
    pr_number: int
    confidence: float


def _build_prompt(issue: dict, candidates: list[FuzzyCandidate]) -> str:
    issue_json = json.dumps({"number": issue["number"], "title": issue["title"]})
    candidates_json = json.dumps(candidates)
    return (
        "An issue has no explicit closing reference from any pull request. Judge whether any of\n"
        "the candidate PRs below likely resolve it, based only on title and branch name similarity.\n\n"
        f"Issue: {issue_json}\n\n"
        f"Candidate PRs: {candidates_json}\n\n"
        "For every candidate, return a confidence between 0 and 1 that it resolves this issue.\n"
        "Return 0 for candidates with no plausible relationship. Do not guess based on PR number\n"
        "proximity alone - only title and branch name similarity count as evidence."
    )


def _validate(parsed: Any, valid_numbers: set[int]) -> list[FuzzyMatch] | None:
    """Returns None for anything that doesn't conform - the caller treats
    that identically to a JSON parse failure (one repair retry, then no
    match). A hallucinated PR number outside the candidate set is dropped
    rather than treated as invalid, since the rest of the response may
    still be trustworthy.
    """
    if not isinstance(parsed, dict) or not isinstance(parsed.get("matches"), list):
        return None

    result: list[FuzzyMatch] = []
    for match in parsed["matches"]:
        if not isinstance(match, dict):
            return None
        pr_number = match.get("pr_number")
        confidence = match.get("confidence")
        if not isinstance(pr_number, int) or isinstance(pr_number, bool):
            return None
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            return None
        if not (0 <= confidence <= 1):
            return None
        if pr_number in valid_numbers:
            result.append({"pr_number": pr_number, "confidence": float(confidence)})

    return result


def match_issue_to_prs(client: anthropic.Anthropic, issue: dict, candidates: list[FuzzyCandidate]) -> list[FuzzyMatch]:
    """A genuine anthropic.APIError (rate limit, auth, 5xx) propagates
    immediately for the orchestrator's own retry/circuit-breaker handling.
    Only a malformed response body is retried here, then treated as no
    match - a missed fuzzy match degrades to "flag: low confidence"
    downstream rather than corrupting the batch.
    """
    if not candidates:
        return []

    prompt = _build_prompt(issue, candidates)
    valid_numbers = {c["number"] for c in candidates}

    for _attempt in range(MAX_ATTEMPTS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": _SCHEMA},
        )
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                pass
            else:
                validated = _validate(parsed, valid_numbers)
                if validated is not None:
                    return validated

    return []
