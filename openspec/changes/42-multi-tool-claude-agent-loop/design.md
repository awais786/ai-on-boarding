## Context

See proposal.md - Why. This capability has no relationship to `sdd_django_demo/`: no HTTP
surface, no ORM, no DRF. It is a new, Django-independent standalone script in a plain
`agent_loop/` folder at the repo root that talks to the real Claude Messages API. This is also
the first place in the repo where a test needs a live network call and an API key
(`ANTHROPIC_API_KEY`) rather than running fully offline.

## Goals / Non-Goals

**Goals:**
- A minimal loop that satisfies every requirement in `specs/multi-tool-agent-loop/spec.md`:
  two schema-valid tools, `stop_reason`-driven termination, correct tool-result threading,
  multi-step support, and the 20-iteration safety cap with a logged warning.
- A test that exercises the exact two-tool transcript from issue #42 against the real API.

**Non-Goals:**
- Domain/region filtering for `web_search` (`allowed_domains`, `user_location`) - not added
  unless a concrete scenario needs it. (Supersedes the original "`web_search` stays a stub"
  non-goal - see the Decisions section below, per the PR #43 review request.)
- A general-purpose expression language for `calculator` - just enough arithmetic to satisfy the
  spec's scenarios.
- Any Django integration, HTTP endpoint, or persistence.

## Decisions

**File layout: new `agent_loop/agent_loop.py`, in a plain folder at the repo root, sibling to
`sdd_django_demo/`.** Nothing here needs Django, DRF, or the ORM, so nesting it inside
`sdd_django_demo/` would add a fake dependency in the other direction (a non-Django module living
inside a Django project). A single standalone script, not a package - `agent_loop/` has no
`__init__.py`; it groups this script with its sibling `enhanced_agent_loop.py` purely for
directory tidiness at the repo owner's request, not to enable imports between them (each still
reads top-to-bottom on its own, per the `enhanced-agent-loop` change's own "not built on top of
`agent_loop.py`" decision). Internally organized into clearly commented sections:
- calculator (tool definition, JSON schema, and the `ast`-based safe-eval implementation)
- dispatch (`TOOLS` list plus `dispatch(name, input)`)
- loop (`run_agent_loop(client, messages, max_iterations=20)`)
- CLI entry point - lets the loop be run by hand (`python agent_loop/agent_loop.py "<prompt>"`) against the
  live API, to manually reproduce the issue's worked example.
- `tests/test_agent_loop.py` - the multi-step test.

**Model: `claude-haiku-4-5-20251001`.** Superseded from an initial choice of `claude-sonnet-5`
during apply: the person running this exercise asked explicitly to keep the live-API calls cheap
and capped the number of live test runs, since every run against the real API costs money.
Sonnet would have been the safer choice for reliably picking the right tool in the right order
(the original rationale still holds in general), but for this repo's two-tool, two-step example
- with a prompt that explicitly names which tool to use at each step (see the live-API test
strategy below) - Haiku is expected to follow the instructed sequence just as reliably at a
fraction of the cost. If a future run shows Haiku picking tools unreliably even with an explicit
prompt, that is grounds to revisit this decision, not to loosen the prompt.

**Calculator: parse with `ast`, evaluate only a whitelisted node set - no `eval`.** Walk the
parsed expression and permit only numeric literals, unary +/-, and binary `+ - * /` and `%`, with
parentheses via normal AST grouping. Reject anything else (names, calls, attributes,
subscripts, comprehensions) as an invalid expression, per the spec's "not by evaluating it as
arbitrary code" requirement. Alternative considered: bare `eval()` with a restricted
`__builtins__` dict - rejected, since that pattern has known sandbox-escape techniques and buys
nothing over a small AST whitelist for the arithmetic this exercise needs.

**Calculator excludes exponentiation (`**`).** The issue's own example (`68000000 * 0.10`) never
needs it, and allowing it re-opens a classic safe-eval denial-of-service (`9**9**9**9`). Division
by zero and any other evaluation error is caught and returned as an error result, per the spec's
"Expression is not arithmetic" scenario, rather than raising out of the tool call.

**Calculator rejects oversized input and non-finite results, so `dispatch()`'s "never raises"
contract holds for anything Claude's tool-call might supply.** Two lightweight checks, added
after a live crash during implementation (see traceability.md): a 200-character cap on the
expression string, rejecting deeply nested or absurdly long input before parsing; and a
finiteness check on the evaluated result, rejecting `inf`/`-inf`/`nan` - e.g. a scientific-notation
literal like `1e400`, which Python's own parser silently overflows to `inf` before any AST-level
guard runs, so it must be caught after evaluation rather than during it. Both exist to keep the
tool from crashing or returning a non-numeric value, not to defend against a hostile actor - the
narrower magnitude/depth-defense question below remains genuinely out of scope.

**Multiple `tool_use` blocks in one response are tagged with their position and the group's
size, not silently dispatched as if unrelated.** Each `tool_use` on_event event gains
`batch_index` (1-based) and `batch_size` (the total number of `tool_use` blocks in that
response); `batch_size == 1` means the tool call arrived alone. The CLI renders this directly
on each `tool_use:` line, e.g. `tool_use (2 of 3 requested together):`, computed per event
rather than tracked as separate before/after banner state. Execution order is unchanged - still
sequential, per the earlier decision not to add concurrency for this exercise's near-instant
stub tools (see the Risks/Trade-offs note on `web_search`/parallel dispatch below). This only
makes the existing behavior observable; it does not change it.

**`web_search` is Anthropic's provider-executed server tool, not a client stub (supersedes the
original stub decision, per the PR #43 review request from the repo owner).** Registered as
`{"type": "web_search_20260209", "name": "web_search", "max_uses": 3, "allowed_callers":
["direct"]}` in `TOOLS` - no `input_schema`, no handler function, no `dispatch()` branch, since
Anthropic's servers execute the search and return a `server_tool_use`/`web_search_tool_result`
block pair within the same response. `max_uses: 3` bounds the number of searches performed for a
single request, mirroring the loop's own iteration cap in spirit. `allowed_callers: ["direct"]`
was added after a live run against `claude-haiku-4-5-20251001` failed with `400 invalid_request_error:
'claude-haiku-4-5-20251001' does not support programmatic tool calling` - a newer Anthropic API
requirement (not present when this tool was first registered) that server tools with
`allowed_callers` must have it set explicitly for models that don't support the
"programmatic"/code-execution calling mode; `["direct"]` matches how this loop actually calls it.
Domain/region filtering (`allowed_domains`, `user_location`) is deliberately left out, per the
review comment's stated non-goal, unless a
concrete scenario needs it.

**Loop control flow:**
```
messages = [initial user message]
for iteration in range(1, MAX_ITERATIONS + 1):
    response = client.messages.create(model=..., tools=TOOLS, messages=messages)
    emit any server_tool_use/web_search_tool_result blocks in response.content (observational
    only - never dispatched, never fed back as a client tool_result) BEFORE emitting text, so a
    search always appears in the transcript before the text that reports on it
    if response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})
        tool_results = [execute each tool_use block via tools.dispatch(...)]
        messages.append({"role": "user", "content": tool_results})
        continue
    if response.stop_reason == "end_turn":
        return text joined from response.content
    # any other stop_reason (e.g. max_tokens) is treated as terminal too:
    # log a warning and return whatever text is present, rather than looping
logger.warning("agent_loop: MAX_ITERATIONS (%d) reached without end_turn", MAX_ITERATIONS)
return best-effort text from the last response
```
Only `tool_use` and `end_turn` are meaningful per the spec; a third `stop_reason` (e.g. the
model hitting `max_tokens`) is not something a retry loop should paper over, so it is treated as
terminal-with-a-warning rather than silently continuing.

**Live-API test strategy (per the chosen approach: real API, not a fake client).** The test:
1. Sends a prompt closely modeled on the issue's transcript, explicitly instructing the model to
   use `web_search` to look up France's population and `calculator` to compute 10% of it, so the
   test does not depend on whether the model would otherwise answer from memorized training data.
2. Asserts on *structure*, not exact wording: that `web_search` was called at least once, that
   `calculator` was called with an expression that numerically evaluates (via the same safe-eval
   the tool itself uses) to 10% of the number the stub `web_search` returned, and that the loop
   terminated via `stop_reason == "end_turn"` rather than the iteration cap.
3. Is skipped (not failed) when `ANTHROPIC_API_KEY` is not set in the environment, so the rest of
   the suite stays runnable without credentials, matching the proposal's Impact note that this is
   the first test in the repo needing a live key.

## Risks / Trade-offs

- **Non-determinism of a live model call** → the test asserts on tool-call structure and computed
  values rather than exact final-answer phrasing, and the prompt explicitly directs which tools
  to use in which order, so the assertions stay meaningful without pinning the model's wording.
- **Live test costs tokens/money and needs network access on every run** → skipped cleanly via
  `pytest.mark.skipif` when no `ANTHROPIC_API_KEY` is present, rather than failing hard for
  contributors without a key.
- **The 200-character length cap and finiteness check are proxies, not semantic bounds** →
  they stop the tool from crashing or returning `inf`/`nan` today, but neither bounds AST depth
  or intermediate magnitude directly. If `**` is ever added to the operator whitelist, a short
  expression like `9**9**9**9` would need a dedicated guard - this cap would not catch it.
  Documented here as a known gap for that future change, not defended against now, since adding
  one would be design creep beyond what today's requirements ask for.
- **Multiple `tool_use` blocks in one response are still dispatched sequentially, not
  concurrently** → each is now labeled with its position in the batch (see the Decisions
  section above), but execution order stays a plain loop. `calculator` calls are near-instant, so
  this costs nothing today; concurrent dispatch was deliberately not added, since it would
  anticipate a future real network-bound client tool this exercise doesn't have - design creep
  beyond what today's requirements ask for, same reasoning as the guard above.
- **`web_search` now makes a real network call with real cost, on every code path that exercises
  it** → unlike the old fixed lookup table, there is no offline mock to fall back on; unit tests
  that need to assert on `web_search` behavior without a live API key must script a fake
  `server_tool_use`/`web_search_tool_result` response rather than calling `tools.dispatch` (there
  is no `web_search` dispatch branch left to call), and the live acceptance test's assertions
  about the returned figure may need to loosen now that the result comes from a real search
  rather than a fixed stub string.
