"""Manual agentic loop around the Claude Messages API.

Selects between the calculator and web_search tools, executes what Claude requests,
and terminates based solely on response.stop_reason.
"""

import logging
import sys

from agent_loop.tools import TOOLS, dispatch_tool

MODEL = "claude-haiku-4-5-20251001"
MAX_ITERATIONS = 20

logger = logging.getLogger(__name__)


def run_agent_loop(user_input: str, client=None) -> str:
    """Run the agentic loop for a single user prompt and return the final text response.

    Terminates normally when a response's stop_reason is "end_turn". MAX_ITERATIONS is a
    safety guardrail only, never the normal completion mechanism.
    """
    if client is None:
        import anthropic

        client = anthropic.Anthropic()

    messages = [{"role": "user", "content": user_input}]

    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            return "".join(
                block.text for block in response.content if block.type == "text"
            )

        if response.stop_reason == "tool_use":
            tool_use_blocks = [
                block for block in response.content if block.type == "tool_use"
            ]

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in tool_use_blocks:
                result_text, is_error = dispatch_tool(block.name, block.input)
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                }
                if is_error:
                    tool_result["is_error"] = True
                tool_results.append(tool_result)

            messages.append({"role": "user", "content": tool_results})
            continue

        # Any other stop_reason (e.g. max_tokens) is not part of the normal
        # tool_use / end_turn lifecycle this loop implements.
        raise RuntimeError(f"Unhandled stop_reason: {response.stop_reason!r}")

    logger.warning(
        "Agent loop reached MAX_ITERATIONS (%d) without an end_turn response; stopping.",
        MAX_ITERATIONS,
    )
    return ""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    prompt = " ".join(sys.argv[1:]) or "Find France population and calculate 10%."
    print(run_agent_loop(prompt))
