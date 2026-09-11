## Purpose

Runs a model in a loop with more than one tool available to it: the model decides which tool it
needs, the tool runs, its result re-enters the conversation, and the model decides again with
that result in hand, until it reports it has finished. The loop's decision to stop is read from
the model's own stop signal, never inferred from the shape or wording of what it wrote.

## ADDED Requirements

### Requirement: Offer a calculator tool
The loop SHALL offer the model a tool named `calculator` that takes a single string input named
`expression` and returns the value of that arithmetic expression. The tool SHALL be declared with
a name, a description of when to use it, and a schema describing its input.

#### Scenario: Tool is declared with its input schema
- **WHEN** the loop presents its tools to the model
- **THEN** `calculator` is among them, carrying a description and a schema that names
  `expression` as a required string

#### Scenario: An arithmetic expression is evaluated
- **WHEN** the model requests `calculator` with the expression `14180000 / 1000`
- **THEN** the result returned to the model is `14180`

### Requirement: Offer a web search tool
The loop SHALL offer the model a tool named `web_search` that takes a single string input named
`query` and returns stub search results for that query. The tool SHALL be declared with a name, a
description of when to use it, and a schema describing its input.

#### Scenario: Tool is declared with its input schema
- **WHEN** the loop presents its tools to the model
- **THEN** `web_search` is among them, carrying a description and a schema that names `query` as
  a required string

#### Scenario: A query returns a stub result
- **WHEN** the model requests `web_search` with any query
- **THEN** a stub result is returned to the model, and no external network request is made

### Requirement: Let the model choose the tool
The loop SHALL NOT decide in advance which tool to use, nor instruct the model to use a
particular tool. Which tool runs, and in what order, SHALL be determined by the model from the
task and the tool descriptions.

#### Scenario: The task determines the tool chosen
- **WHEN** a task is given that requires looking up a value the model was not given, and then
  performing arithmetic on it
- **THEN** the model requests `web_search` before it requests `calculator`

### Requirement: Execute every requested tool and return its result
When the model requests one or more tools, the loop SHALL execute each request and return each
result identified by the same request it answers.

#### Scenario: A requested tool is executed
- **WHEN** the model requests a tool with a given input
- **THEN** that tool runs with that input, and its output is returned to the model against the
  identifier of the request it answers

#### Scenario: A tool that cannot run reports an error rather than ending the run
- **WHEN** the model requests a tool that does not exist, or supplies input the tool cannot use
- **THEN** an error result is returned to the model for that request, and the loop continues

### Requirement: Thread results back into the conversation
The loop SHALL add the model's response to the conversation in full before adding the results of
the tools it requested, so the model sees its own request alongside the answer to it.

#### Scenario: The model's response is preserved in full
- **WHEN** the model's response is added to the conversation
- **THEN** every part of that response is preserved unchanged, including any reasoning content it
  produced alongside the tool request

#### Scenario: All results for one response are returned together
- **WHEN** a single response requests more than one tool
- **THEN** the results for all of them are returned in one turn, not spread across several

### Requirement: Terminate only on the model's reported stop reason
The loop SHALL end normally only when the model reports that it has finished its turn. The loop
SHALL NOT end because of the type of any content the model produced, because of any wording in
its text, or because a number of turns has elapsed.

#### Scenario: A response that both writes text and requests a tool continues the loop
- **WHEN** the model reports it is requesting a tool, and the first part of its response is text
  rather than the tool request
- **THEN** the loop executes the requested tool and continues

#### Scenario: A finished turn returns the model's answer
- **WHEN** the model reports it has finished its turn
- **THEN** the loop stops and returns the text of that response to the caller

### Requirement: Support several tool calls in sequence
The loop SHALL support a task that needs more than one tool call to complete, where a value
obtained from one tool is used in a later call to another.

#### Scenario: A value found by one tool is used by the next
- **WHEN** a task requires searching for a value and then computing with it
- **THEN** the loop performs the search, returns its result, performs the calculation using that
  value, and returns a final answer

### Requirement: Cap the number of iterations for safety
The loop SHALL stop after at most 20 iterations. This cap is a safeguard against a run that
cannot finish; it SHALL NOT be the means by which a normal run ends.

#### Scenario: A normal run finishes before the cap
- **WHEN** a task completes normally
- **THEN** the loop ends because the model reported it had finished, having used fewer than 20
  iterations

#### Scenario: Reaching the cap is reported, not returned as an answer
- **WHEN** the loop reaches 20 iterations without the model reporting it has finished
- **THEN** a warning is recorded, and the caller is told the run was capped rather than receiving
  a result indistinguishable from a completed one

### Requirement: Report a response the loop cannot act on
The loop SHALL report, rather than treat as a normal ending, any response it cannot act on: a
stop reason it does not recognise, or a report of a tool request that carries no tool to run.

#### Scenario: An unrecognised stop reason is reported
- **WHEN** the model reports a stop reason that is neither "finished" nor "requesting a tool"
- **THEN** the loop stops, records what the stop reason was, and does not present the response as
  a completed answer

#### Scenario: A tool request naming no tool is reported
- **WHEN** the model reports it is requesting a tool but the response contains no tool request
- **THEN** the loop stops and records the anomaly, and sends no empty turn back to the model

### Requirement: Evaluate expressions without executing arbitrary code
The `calculator` tool SHALL evaluate arithmetic only. It SHALL refuse any input that would
execute code, reach attributes, or call functions, and SHALL refuse it without executing it.

#### Scenario: Input that is not arithmetic is refused
- **WHEN** the expression contains anything other than numbers, arithmetic operators and
  parentheses - for example an attribute access, a name, or a function call
- **THEN** the tool returns an error result and evaluates nothing

#### Scenario: Arithmetic that cannot produce a real value is refused
- **WHEN** the expression is arithmetically invalid, such as dividing by zero, or would produce
  something other than a real number, such as raising a negative number to a fractional power
- **THEN** the tool returns an error result rather than raising or answering with that value

### Requirement: Refuse an expression whose result would be too large to compute
The `calculator` tool SHALL refuse an expression whose evaluation would require unbounded time or
memory, and SHALL refuse it *before* attempting that evaluation. The expression is chosen by the
model, so the tool SHALL return promptly whatever it is given.

#### Scenario: A power with an enormous result is refused
- **WHEN** the expression raises a number to a power whose result would be too large to compute,
  such as `2 ** 999999999`
- **THEN** the tool returns an error result promptly, having attempted no part of the computation

#### Scenario: Ordinary arithmetic is unaffected
- **WHEN** the expression is ordinary arithmetic well within that bound, such as `2 ** 10`
- **THEN** it is evaluated normally and returns `1024`

### Requirement: Demonstrate the complete lifecycle against a live model
The capability SHALL include a check that drives the whole lifecycle - tool choice, execution,
result, further tool choice, final answer - against a live model, and SHALL state plainly when
that check has not been performed.

#### Scenario: The lifecycle is verified when a live model is reachable
- **WHEN** the checks are run and a credential for a live model is available
- **THEN** the full multi-tool lifecycle is exercised against that model and must pass

#### Scenario: An unperformed check is reported, not passed over
- **WHEN** the checks are run and no credential for a live model is available
- **THEN** the run reports that the live lifecycle check did not run and which requirement is
  therefore unverified, rather than omitting it without comment
