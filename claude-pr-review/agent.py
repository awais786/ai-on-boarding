"""The one agentic loop both the judge and verify agents run - a manual
loop (not the SDK's beta tool_runner) so `output_config.format` (structured
outputs) can be combined with tool use on every request without relying on
undocumented behavior of a beta helper. Tool calls have no text content, so
the schema constraint only ever binds the model's final answer.
"""
from __future__ import annotations

import json

import tools

MAX_ITERATIONS = 15
MAX_TOKENS = 8000


class AgentError(RuntimeError):
    pass


def run(client, model: str, system: str, user_content: str, output_schema: dict) -> dict:
    messages = [{"role": "user", "content": user_content}]

    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=tools.TOOLS,
            output_config={"format": output_schema},
            messages=messages,
        )

        if response.stop_reason == "refusal":
            raise AgentError(f"Model declined: {response.stop_details}")

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": tools.execute(block.name, block.input),
                }
                for block in response.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "user", "content": tool_results})
            continue

        if response.stop_reason == "max_tokens":
            raise AgentError("Hit max_tokens before producing a final answer")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise AgentError(f"No text content in final response (stop_reason={response.stop_reason})")
        return json.loads(text)

    raise AgentError(f"Exceeded {MAX_ITERATIONS} tool-use iterations without a final answer")
