# Traceability: build-multi-tool-agent-loop

Maps every requirement in `specs/multi-tool-agent-loop/spec.md` to its implementation and tests.

| Requirement | Code | Tests |
| --- | --- | --- |
| Tool Definitions | `agent_loop/tools.py` — `CALCULATOR_TOOL`, `WEB_SEARCH_TOOL`, `TOOLS` | `test_tool_definitions_have_valid_json_schema`, `test_lifecycle_web_search_then_calculator_then_end_turn` |
| Stop-Reason-Driven Loop Termination | `agent_loop/loop.py` — `run_agent_loop` (branches only on `response.stop_reason`) | `test_lifecycle_web_search_then_calculator_then_end_turn`, `test_end_turn_termination_does_not_depend_on_content_order` |
| Tool Use Extraction and Execution | `agent_loop/loop.py` — `run_agent_loop` (`tool_use` branch: extracts blocks, appends assistant response, appends `tool_result` message with matching `tool_use_id`) | `test_lifecycle_web_search_then_calculator_then_end_turn`, `test_multiple_tool_use_blocks_in_one_response_are_all_executed` |
| Tool Dispatcher and Unknown Tool Handling | `agent_loop/tools.py` — `calculator`, `web_search`, `dispatch_tool` | `test_dispatch_tool_routes_calculator`, `test_dispatch_tool_routes_web_search`, `test_dispatch_tool_malformed_input_does_not_crash_the_loop`, `test_dispatch_tool_unknown_name_is_not_silently_ignored` |
| Multi-Step Sequential Tool Calls | `agent_loop/loop.py` — `run_agent_loop` (loop continues across `tool_use` turns, prior `tool_result`s feed the next request) | `test_lifecycle_web_search_then_calculator_then_end_turn` |
| Safety Iteration Cap | `agent_loop/loop.py` — `MAX_ITERATIONS`, the bounded `for` loop, and the warning `logger.warning(...)` on exhaustion | `test_lifecycle_web_search_then_calculator_then_end_turn` (finishes well under the cap), `test_max_iterations_reached_stops_and_logs_warning` |
