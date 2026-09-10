"""The agentic loop judge.py and verify.py both run: read-only tool use plus
a JSON-schema-constrained final answer, via a manual loop rather than the
SDK's beta tool_runner so output_config and tools can be combined safely.
"""
from __future__ import annotations

import json
import sys

import tools

MAX_ITERATIONS = 30
MAX_TOKENS = 8000

# Task budgets (beta): a total token ceiling for the whole loop that Claude
# paces itself against, instead of a fixed per-response cap. Only on models
# that support the beta - Opus 5, Sonnet 5, Fable 5/5.1, Opus 4.7/4.8, not
# Haiku - so it's opt-in per caller via run()'s task_budget arg.
TASK_BUDGET_BETA = "task-budgets-2026-03-13"
MIN_TASK_BUDGET_TOKENS = 20_000

FINDING = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": ["CRITICAL", "MAJOR", "MINOR"]},
        "summary": {"type": "string"},
        "citation": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "The exact requirement, named failing test, or quoted convention text this finding is based on, or null if none applies.",
        },
        "file": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "line": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
    },
    "required": ["severity", "summary", "citation", "file", "line"],
    "additionalProperties": False,
}

FINDINGS_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {"findings": {"type": "array", "items": FINDING}},
        "required": ["findings"],
        "additionalProperties": False,
    },
}


class AgentError(RuntimeError):
    pass


def run(
    client,
    model: str,
    system: str,
    user_content: str,
    output_schema: dict = FINDINGS_SCHEMA,
    task_budget: int | None = None,
) -> dict:
    """Run the tool-use loop. `task_budget`, if given, is a total token
    ceiling (>= MIN_TASK_BUDGET_TOKENS) for the whole loop - the server
    tracks spend across iterations from the resent history, so leave it
    None on a model that doesn't support the beta.
    """
    if task_budget is not None and task_budget < MIN_TASK_BUDGET_TOKENS:
        raise ValueError(f"task_budget must be at least {MIN_TASK_BUDGET_TOKENS} tokens")

    # cache_control here caches tools + system prompt + this message together.
    # As the loop appends tool calls/results, the marker moves to the newest
    # block each iteration (and is cleared off the old one, to stay under the
    # 4-breakpoint cap) - otherwise only turn 1 would ever be cached, and
    # every later turn would resend the whole growing tail at full price.
    first_block = {"type": "text", "text": user_content, "cache_control": {"type": "ephemeral"}}
    messages = [{"role": "user", "content": [first_block]}]
    cached_block = first_block

    for iteration in range(1, MAX_ITERATIONS + 1):
        if task_budget is None:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=tools.TOOLS,
                output_config={"format": output_schema},
                messages=messages,
            )
        else:
            output_config = {
                "format": output_schema,
                "task_budget": {"type": "tokens", "total": task_budget},
            }
            with client.beta.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=tools.TOOLS,
                output_config=output_config,
                betas=[TASK_BUDGET_BETA],
                messages=messages,
            ) as stream:
                response = stream.get_final_message()

        if response.stop_reason == "refusal":
            raise AgentError(f"Model declined: {response.stop_details}")

        if response.stop_reason == "tool_use":
            calls = [b for b in response.content if b.type == "tool_use"]
            print(
                f"[agent] iteration {iteration}/{MAX_ITERATIONS}: "
                + ", ".join(f"{c.name}({c.input})" for c in calls),
                file=sys.stderr,
            )
            messages.append({"role": "assistant", "content": response.content})
            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tools.execute(block.name, block.input),
                }
                for block in calls
            ]
            messages.append({"role": "user", "content": tool_results})

            cached_block.pop("cache_control", None)
            tool_results[-1]["cache_control"] = {"type": "ephemeral"}
            cached_block = tool_results[-1]
            continue

        if response.stop_reason == "max_tokens":
            raise AgentError("Hit max_tokens before producing a final answer")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise AgentError(f"No text content in final response (stop_reason={response.stop_reason})")
        return json.loads(text)

    raise AgentError(f"Exceeded {MAX_ITERATIONS} tool-use iterations without a final answer")
