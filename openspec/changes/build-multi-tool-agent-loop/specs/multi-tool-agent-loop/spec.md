## Purpose

Defines a Claude Messages API agentic loop that lets Claude choose between a `calculator` tool and
a `web_search` tool, executes the tool(s) it requests, feeds the results back, and terminates
normally only when the API reports the turn is complete.

## ADDED Requirements

### Requirement: Tool Definitions
The system SHALL define a `calculator` tool and a `web_search` tool, each with a `name`, a
`description`, and a valid JSON Schema `input_schema`, and SHALL pass both tool definitions to the
Claude Messages API on every request in the loop. `calculator`'s `input_schema` SHALL require a
string `expression` field. `web_search`'s `input_schema` SHALL require a string `query` field.

#### Scenario: Both tools are offered on every request
- **WHEN** the loop sends a request to the Messages API
- **THEN** the request's `tools` list contains both the `calculator` and `web_search` definitions,
  each with `name`, `description`, and `input_schema` populated

#### Scenario: Claude selects the tool appropriate to the task
- **WHEN** the user prompt requires looking up a fact before computing a value (for example,
  "Find France population and calculate 10%.")
- **THEN** Claude's first tool request names `web_search`, and a later tool request in the same
  conversation names `calculator`

### Requirement: Stop-Reason-Driven Loop Termination
The system SHALL determine whether to continue or stop the loop solely from
`response.stop_reason`: it SHALL continue the loop when `stop_reason == "tool_use"` and SHALL
return the final text response and stop the loop when `stop_reason == "end_turn"`. The system
SHALL NOT use `response.content[0].type`, natural-language phrases in Claude's text (e.g. "I'm
done"), or a fixed iteration count as the mechanism for normal termination.

#### Scenario: tool_use keeps the loop running
- **WHEN** a response has `stop_reason == "tool_use"`
- **THEN** the loop executes the requested tool(s) and sends another request rather than stopping

#### Scenario: end_turn stops the loop and returns the final answer
- **WHEN** a response has `stop_reason == "end_turn"`
- **THEN** the loop stops and returns the text content of that response as the final result

### Requirement: Tool Use Extraction and Execution
When a response's `stop_reason` is `"tool_use"`, the system SHALL extract every `tool_use` content
block from that response, execute each requested tool, append the complete assistant response
(including its `tool_use` blocks) to the conversation history, and append a single subsequent user
message containing one `tool_result` block per executed tool, each carrying the `tool_use_id` of
the `tool_use` block it answers.

#### Scenario: A single tool_use block is executed and answered
- **WHEN** a response contains one `tool_use` block requesting `web_search`
- **THEN** the conversation history gains the assistant's response followed by a user message
  containing exactly one `tool_result` block whose `tool_use_id` matches that `tool_use` block's id

#### Scenario: Multiple tool_use blocks in one response are all executed
- **WHEN** a response contains more than one `tool_use` block
- **THEN** every requested tool is executed, and the following user message contains one
  `tool_result` block for each of them, each with the matching `tool_use_id`

### Requirement: Tool Dispatcher and Unknown Tool Handling
The system SHALL provide separate implementations for the `calculator` and `web_search` tools and
SHALL route each requested tool name to its implementation through a single dispatcher. When the
dispatcher receives a tool name that is neither `calculator` nor `web_search`, it SHALL NOT
silently ignore the request; it SHALL produce a `tool_result` for that `tool_use_id` that reports
the tool as unrecognized.

#### Scenario: calculator requests are routed to the calculator implementation
- **WHEN** a `tool_use` block names `calculator` with an `expression` input
- **THEN** the dispatcher invokes the calculator implementation and returns its result as that
  block's `tool_result`

#### Scenario: web_search requests are routed to the web_search implementation
- **WHEN** a `tool_use` block names `web_search` with a `query` input
- **THEN** the dispatcher invokes the web_search implementation and returns its result as that
  block's `tool_result`

#### Scenario: An unrecognized tool name is not silently ignored
- **WHEN** a `tool_use` block names a tool that is neither `calculator` nor `web_search`
- **THEN** the dispatcher returns a `tool_result` for that block's `tool_use_id` indicating the
  tool name is unrecognized, and the loop continues rather than crashing or dropping the request

### Requirement: Multi-Step Sequential Tool Calls
The system SHALL support a conversation in which Claude issues more than one tool call in
sequence within the same loop run, with each later tool call able to use information returned by
an earlier tool's result.

#### Scenario: A calculator call uses a value obtained from an earlier web_search result
- **WHEN** Claude's first tool call is `web_search` and the resulting `tool_result` contains a
  numeric value
- **THEN** Claude's next tool call is `calculator`, and its `expression` input incorporates the
  value returned by the `web_search` tool result

### Requirement: Safety Iteration Cap
The system SHALL enforce a `MAX_ITERATIONS` safety cap of 20 loop iterations, used only to guard
against a runaway loop. A request that behaves normally SHALL terminate via
`stop_reason == "end_turn"` before reaching this cap. If the loop reaches `MAX_ITERATIONS` without
an `end_turn` response, the system SHALL stop execution and log a warning; it SHALL NOT treat
reaching `MAX_ITERATIONS` as a normal, expected way for a request to finish.

#### Scenario: Normal requests finish well under the cap
- **WHEN** a request follows the expected tool_use/tool_result exchange pattern
- **THEN** the loop terminates via `stop_reason == "end_turn"` in fewer than `MAX_ITERATIONS`
  iterations

#### Scenario: Reaching the cap stops execution and logs a warning
- **WHEN** the loop completes `MAX_ITERATIONS` iterations without receiving `stop_reason ==
  "end_turn"`
- **THEN** the loop stops making further requests and logs a warning noting the safety limit was
  reached
