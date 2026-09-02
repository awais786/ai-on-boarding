## 1. Package Scaffolding

- [x] 1.1 Create `agent_loop/` at the repo root with `__init__.py`, `tools.py`, `loop.py`, and
  `requirements.txt` (`anthropic`, `pytest`); verify the package imports cleanly
  (`python -c "import agent_loop"`)
- [x] 1.2 Add a short `agent_loop/README.md` documenting how to install dependencies, set
  `ANTHROPIC_API_KEY`, run the loop, and run its tests

## 2. Tools

- [x] 2.1 In `agent_loop/tools.py`, define the `calculator` and `web_search` tool schemas (each
  with `name`, `description`, `input_schema`) as a `TOOLS` list; verify each `input_schema` is
  valid JSON Schema (`expression`/`query` required string fields)
- [x] 2.2 Implement `calculator(expression: str)` using a restricted `ast`-based evaluator
  (numeric literals and `+ - * / ** ()` / unary +/- only); reject any other node type and catch
  evaluation errors, returning a clear error string rather than raising
- [x] 2.3 Implement `web_search(query: str)` as a stub returning a canned string for a
  France-population query and a generic "no results" string otherwise, with no network call
- [x] 2.4 Implement `dispatch_tool(name: str, tool_input: dict) -> tuple[str, bool]` (result
  text, `is_error` flag) that routes `calculator`/`web_search` to their implementations and
  returns an explicit "unrecognized tool" error (not a silent no-op) for any other name

## 3. Agentic Loop

- [x] 3.1 In `agent_loop/loop.py`, define `MODEL = "claude-opus-5"` and `MAX_ITERATIONS = 20`
- [x] 3.2 Implement `run_agent_loop(user_input: str, client=None) -> str`: builds the initial
  `messages` list, calls `client.messages.create(model=MODEL, tools=TOOLS, messages=messages,
  ...)` in a loop bounded by `MAX_ITERATIONS`
- [x] 3.3 On `stop_reason == "tool_use"`: extract all `tool_use` blocks, append the assistant's
  full response to `messages`, call `dispatch_tool` for each block, and append one user message
  containing all resulting `tool_result` blocks (each with the matching `tool_use_id` and
  `is_error` when applicable)
- [x] 3.4 On `stop_reason == "end_turn"`: return the response's text content and stop, without
  inspecting `content[0].type` or any natural-language phrase to decide this
- [x] 3.5 If the loop reaches `MAX_ITERATIONS` without an `end_turn` response, stop issuing
  requests and log a warning via `logging.getLogger(__name__)`
- [x] 3.6 Add a `if __name__ == "__main__":` entry point that reads a prompt (e.g. from `sys.argv`)
  and prints the result of `run_agent_loop`, for manual/documented runs against the live API

## 4. Tests (after implementation, from the spec)

- [x] 4.1 List every requirement in `specs/multi-tool-agent-loop/spec.md` and what a test would
  need to assert, working only from the spec
- [x] 4.2 Write `agent_loop/test_agent_loop.py` from that list, mocking
  `client.messages.create` (per design.md Decision 5) to script the
  `web_search → calculator → end_turn` lifecycle for "Find France population and calculate 10%.";
  assert: `web_search` requested first, its `tool_result` appended with the matching
  `tool_use_id`, `calculator` requested next with an `expression` that incorporates the value from
  the `web_search` result, its `tool_result` appended with the matching `tool_use_id`, the final
  `stop_reason == "end_turn"`, and the returned text contains the calculated result — without
  asserting on Claude's exact wording
- [x] 4.3 Write a unit test asserting `dispatch_tool` returns an explicit error (not a silent
  no-op) for an unrecognized tool name
- [x] 4.4 Write a unit test asserting the loop stops and logs a warning when `MAX_ITERATIONS` is
  reached without an `end_turn` response (mock `client.messages.create` to always return
  `stop_reason == "tool_use"`)
- [x] 4.5 Run `pytest agent_loop/` and confirm all tests pass
- [x] 4.6 Prove the lifecycle test can actually fail — temporarily break the `tool_use_id`
  pairing or the `stop_reason` check, confirm the test goes red, then restore it

## 5. Traceability and Review

- [x] 5.1 Build `traceability.md` mapping every requirement in
  `specs/multi-tool-agent-loop/spec.md` to its code and test
- [x] 5.2 Run `/code-review` and address any finding that cites a requirement, a specific failing
  test, or a documented convention
- [x] 5.3 Re-run `/code-review` (verify-only pass) until it returns `Ready to merge: yes`
