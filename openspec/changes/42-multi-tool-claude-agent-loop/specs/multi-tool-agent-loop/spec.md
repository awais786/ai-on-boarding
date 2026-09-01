## Purpose

Lets a caller send a conversation to Claude with a calculator and a web-search tool available,
have whichever tool Claude requests executed automatically, and get back Claude's final answer
once it has finished using tools - without the caller having to guess at completion from
anything other than the model's own signal.

## ADDED Requirements

### Requirement: Register a calculator tool
The system SHALL register a tool named `calculator` with a description and an `input_schema`
requiring a single string property `expression`, and it SHALL return the numeric result of
evaluating that expression as a mathematical expression - not by evaluating it as arbitrary code.

#### Scenario: Valid arithmetic expression
- **WHEN** the calculator tool is invoked with `expression` set to `"68000000 * 0.10"`
- **THEN** it returns `6800000`

#### Scenario: Expression is not arithmetic
- **WHEN** the calculator tool is invoked with an `expression` that is not a valid mathematical
  expression (for example, one containing letters, or an attempt to reference code such as
  `__import__` or a function call)
- **THEN** it returns an error result rather than executing anything, and the conversation
  continues with that error as the tool result

### Requirement: Register a web-search tool
The system SHALL register a tool named `web_search` with a description and an `input_schema`
requiring a single string property `query`, and it SHALL return a stubbed/mocked search result
for that query rather than calling any real external search service.

#### Scenario: Search query submitted
- **WHEN** the web_search tool is invoked with a `query`
- **THEN** it returns a mock result string relevant to that query, with no outbound network call
  to a search engine

### Requirement: Execute a requested tool and return its result
When Claude's response has `stop_reason` equal to `tool_use`, the system SHALL extract every
`tool_use` content block, execute the tool it names with the input it supplies, append Claude's
assistant message to the conversation, append a `user` message containing the corresponding
`tool_result` block(s), and send the updated conversation back to Claude.

#### Scenario: Single tool call requested
- **WHEN** Claude's response has `stop_reason == "tool_use"` and one `tool_use` block naming a
  registered tool
- **THEN** that tool is executed with the given input, and the next request to Claude includes
  both Claude's assistant message and a user message carrying the `tool_result`

### Requirement: Indicate when multiple tools are requested in a single turn
When one response from Claude contains more than one `tool_use` block, the system SHALL make
that fact observable for each of those tool calls, distinguishing it from a tool call that
arrived alone in its own turn - rather than presenting every tool call identically regardless of
whether it was requested together with others. This is distinct from the "Support multiple
sequential tool calls" requirement below, which concerns tool calls spread across separate round
trips, not multiple `tool_use` blocks within one response.

#### Scenario: Two tools requested in one turn
- **WHEN** Claude's response has `stop_reason == "tool_use"` and contains two `tool_use` blocks
- **THEN** the output for each of those two tool calls indicates it was one of two tools
  requested together in that turn

#### Scenario: Single tool requested
- **WHEN** Claude's response has `stop_reason == "tool_use"` and contains exactly one `tool_use`
  block
- **THEN** the output for that tool call carries no "requested together" indication,
  distinguishing it from the two-tool case

### Requirement: Terminate only on end_turn
The system SHALL terminate the loop and return Claude's final text response only when a
response's `stop_reason` equals `end_turn`. It SHALL NOT use the content type of the first
content block (e.g. checking for `type == "text"`), nor any natural-language phrase in the
response text (e.g. "I'm done"), as a signal to terminate.

#### Scenario: Model signals completion
- **WHEN** Claude's response has `stop_reason == "end_turn"`
- **THEN** the loop stops and returns the text content of that response as the final answer

#### Scenario: Text appears before tool use concludes
- **WHEN** a response contains a text content block alongside a `tool_use` block and
  `stop_reason == "tool_use"`
- **THEN** the loop still executes the requested tool and continues, rather than treating the
  presence of text content as completion

### Requirement: Support multiple sequential tool calls
The system SHALL support any number of sequential tool-use round trips - each ending in a
`tool_result` fed back to Claude - before the loop terminates via `end_turn`, without requiring
that a request use only one tool or be answerable in a single tool call.

#### Scenario: Two different tools used in sequence
- **WHEN** a request requires first calling `web_search` to obtain a value and then calling
  `calculator` using that value
- **THEN** the loop executes `web_search`, feeds back its result, executes `calculator` with a
  value derived from that result, feeds back its result, and only then terminates on `end_turn`
  with a final answer reflecting both steps

### Requirement: Enforce a maximum iteration safety cap
The system SHALL stop the loop and log a warning if it completes 20 round trips to Claude
without having received a response with `stop_reason == "end_turn"`. This cap exists only as a
safety guardrail; it SHALL NOT be relied upon as the normal way a request finishes, and a request
answerable in fewer round trips SHALL terminate via `end_turn` before reaching it.

#### Scenario: Safety cap reached
- **WHEN** 20 round trips to Claude have completed and no response has had
  `stop_reason == "end_turn"`
- **THEN** the loop stops, logs a warning noting the cap was reached, and does not make a 21st
  request

#### Scenario: Normal request stays well under the cap
- **WHEN** a request requires two sequential tool calls (as in the France-population example)
- **THEN** the loop terminates via `end_turn` in a small, fixed number of round trips, well
  before the 20-iteration cap is reached
