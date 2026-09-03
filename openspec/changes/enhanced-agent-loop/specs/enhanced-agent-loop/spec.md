## Purpose

Extends the base ask -> dispatch -> observe -> repeat agent loop with a real web-search tool,
dispatch-boundary argument validation, and few-shot prompting, so malformed tool calls fail
safely and ambiguous requests reliably resolve `web_search` before `calculator`.

## ADDED Requirements

### Requirement: Provide a real web-search tool via DuckDuckGo
The system SHALL implement `web_search(query)` by calling DuckDuckGo's free Instant Answer API
(`https://api.duckduckgo.com/?q=<query>&format=json&no_html=1`) and SHALL return the response's
`AbstractText`, or a fallback string when `AbstractText` is empty - never a mocked or fixed
result.

#### Scenario: Query returns an abstract
- **WHEN** `web_search` is called with a query DuckDuckGo has an instant-answer abstract for
- **THEN** it returns that `AbstractText`

#### Scenario: Query returns no abstract
- **WHEN** DuckDuckGo's response has an empty `AbstractText` for the query
- **THEN** `web_search` returns a fallback string rather than an empty result

### Requirement: web_search never raises
The system SHALL wrap every DuckDuckGo request in error handling and SHALL return a typed error
string instead of raising, for any failure mode (timeout, DNS/connection failure, or a response
that cannot be parsed as JSON).

#### Scenario: Request fails
- **WHEN** the DuckDuckGo request times out, fails to resolve/connect, or returns a response that
  cannot be parsed as JSON
- **THEN** `web_search` returns an error string identifying the failure type, and does not raise
  an exception

### Requirement: Validate tool arguments at the dispatch boundary
The system SHALL run `validate_args(name, args)` before executing `calculator` or `web_search`,
and SHALL reject and return an error string - without calling the real tool - when the relevant
argument (`expression` for `calculator`, `query` for `web_search`) is missing, not a string,
empty, or exceeds a fixed maximum length.

#### Scenario: Malformed calculator call
- **WHEN** `calculator` is invoked with an empty, non-string, or oversized `expression`
- **THEN** `validate_args` rejects it before `calculator` runs, and the loop observes a
  validation error rather than a crash or a real calculation

#### Scenario: Malformed web_search call
- **WHEN** `web_search` is invoked with an empty, non-string, or oversized `query`
- **THEN** `validate_args` rejects it before `web_search` runs, and the loop observes a
  validation error rather than a crash or a real DuckDuckGo request

### Requirement: Steer tool ordering with a few-shot example
The system SHALL prepend exactly one user/assistant message pair - demonstrating the correct
`web_search` -> `calculator` order for an ambiguous request - to the conversation before the real
user message, on every run.

#### Scenario: Ambiguous request resolves web_search before calculator
- **WHEN** an ambiguous request that needs both a lookup and a calculation is sent, tested across
  at least 3 differently-worded phrasings
- **THEN** the loop invokes `web_search` before `calculator` in each of those runs

### Requirement: Run as a standalone script
The system SHALL provide a command-line entry point invoked as
`python agent_loop/enhanced_agent_loop.py "<prompt>"` that drives the loop end-to-end and
completes without crashing, printing an `[action] web_search(...)` step whenever the search tool
is used.

#### Scenario: End-to-end run completes
- **WHEN** `enhanced_agent_loop.py` is run with a prompt requiring both tools (e.g. "what is
  France's population, divided by 1000?")
- **THEN** it completes without crashing and prints an `[action] web_search(...)` step showing a
  real, non-mocked result
