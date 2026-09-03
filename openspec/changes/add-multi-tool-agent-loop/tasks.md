## 1. Package scaffold

- [x] 1.1 Create `agent_loop/` with `__init__.py` and a `requirements.txt` pinning the Anthropic
  SDK and pytest; verify `python3 -m venv agent_loop/.venv` followed by
  `agent_loop/.venv/bin/pip install -r agent_loop/requirements.txt` succeeds and
  `agent_loop/.venv/bin/python -c "import anthropic"` runs clean
- [x] 1.2 Add `agent_loop/.venv/` to `.gitignore`; verify `git status --short` reports no files
  from the virtual environment

## 2. Tools

- [x] 2.1 Implement the `calculator` tool, parsing the expression into a syntax tree and walking
  it so that only numeric literals, the arithmetic operators and parentheses are permitted;
  verify by hand that `14180000 / 1000` returns `14180`, and that an attribute access such as
  `().__class__` is refused with an error result without being evaluated
- [x] 2.2 Implement the `web_search` tool returning stub results for a query with no network
  access; verify by hand that a known query returns its stub result and an unmatched query
  returns a fallback
- [x] 2.3 Declare both tools with a name, a description stating when the model should call them,
  and an input schema; verify each declaration names its one required string input
  (`expression`, `query`)
- [x] 2.4 Implement dispatch from a requested tool name to its function, returning an error result
  for an unknown tool or for input the tool cannot use rather than raising; verify by hand that
  dispatching an unknown name and a malformed input both return error results
- [x] 2.5 Refuse a power whose result would be too large to compute, predicting the result's size
  from the base's bit length and the exponent before evaluating anything; verify by hand that
  `2 ** 999999999` returns an error promptly and that `2 ** 10` still returns `1024`

## 3. The loop

- [x] 3.1 Implement the request cycle and the stop-reason branch - the requesting-a-tool value
  executes tools and continues, the finished value returns the response text, and every other
  value is logged and stops the run; verify by running the module by hand and observing the stop
  reason reported at each iteration
- [x] 3.2 Append the model's response content whole before appending all of that response's tool
  results as a single turn; verify by hand that a task needing two tools completes end to end
- [x] 3.3 Guard the anomaly where the stop reason reports a tool request but the response carries
  none - log it and stop, never sending a turn with no results; verify by hand by feeding the
  loop a response of that shape
- [x] 3.4 Implement `MAX_ITERATIONS = 20` so reaching it logs a warning and raises
  `IterationLimitExceeded`; verify by hand that a capped run raises rather than returning
- [x] 3.5 Default the model to `claude-haiku-4-5`, overridable through `AGENT_LOOP_MODEL`, and
  send no effort parameter; verify by hand that a run with the variable set uses the named model
- [x] 3.6 Add a command-line entry point that prints the iteration number, stop reason, each tool
  call and its result; verify by hand that a two-tool task prints a three-iteration transcript
  ending in the final answer

## 4. Tests (after implementation, from the spec)

- [x] 4.1 List every requirement in `specs/multi-tool-agent-loop/spec.md` and what a test would
  need to assert, working only from the spec
- [x] 4.2 Write a stub client returning scripted responses, and the tests from that list, covering
  every requirement except *Let the model choose the tool*; verify the suite passes with no
  credential set
- [x] 4.3 Write the live lifecycle check, gated on `ANTHROPIC_API_KEY`, asserting the sequence of
  tool names requested and that the run completes; verify it passes with the credential present
- [x] 4.4 Make the run name the unverified requirement when the credential is absent rather than
  omitting the check without comment; verify by running with `ANTHROPIC_API_KEY` unset and
  confirming the report names *Let the model choose the tool*
- [x] 4.5 Run the suite both with and without the credential; confirm it passes in both cases and
  that only the second reports an unverified requirement
- [x] 4.6 Prove at least one test can fail - break the stop-reason branch on purpose so the loop
  ends on the wrong value, confirm the test protecting *Terminate only on the model's reported
  stop reason* goes red, then restore it
- [x] 4.7 Write tests for *Refuse an expression whose result would be too large to compute*,
  asserting that an enormous power is refused within a time bound and that ordinary arithmetic,
  including a nested power, is unaffected; verify the suite still passes

## 5. Traceability, review, and the change request

- [x] 5.1 Build `traceability.md` mapping every requirement in the delta spec to the code and the
  test that covers it
- [x] 5.2 Run `/code-review` and fix every blocking finding it cites
- [x] 5.3 Run `/code-review` a second time, verify-only, and require a `Ready to merge: yes`
  verdict before opening a pull request
- [x] 5.4 Post the proposal and the full delta spec to issue #42 so the issue is self-contained -
  deferred by request until the specs and implementation are final, rather than done at the point
  the artifacts were written
