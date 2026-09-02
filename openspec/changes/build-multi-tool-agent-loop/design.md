## Context

See proposal.md - Why. This lives in a new top-level `agent_loop/` package at the repo root,
independent of `sdd_django_demo/` (confirmed with the user: this capability is unrelated to the
auth-API domain and gets its own package rather than a new Django app). It has its own
dependencies and its own way of running its test(s); it does not touch Django, its models, or
`sdd_django_demo/pytest.ini`.

## Goals / Non-Goals

**Goals:**
- Satisfy every requirement in `specs/multi-tool-agent-loop/spec.md` with a manual loop around
  `client.messages.create()`, matching the exact lifecycle the proposal specifies.
- Make the multi-step lifecycle test deterministic and runnable offline (no live network call, no
  `ANTHROPIC_API_KEY` required to run the test suite).

**Non-Goals:**
- A real (non-mock) `web_search` implementation — the spec explicitly calls for mock/stub results.
- Using the Anthropic SDK's beta Tool Runner (`client.beta.messages.tool_runner`) — see Decisions.
- Packaging/publishing `agent_loop/` as a distributable library, a CLI framework, or persistence of
  conversation history across process runs.
- Any change to `sdd_django_demo/`.

## Decisions

**1. Manual loop, not the Tool Runner.**
The Anthropic Python SDK's beta Tool Runner (`client.beta.messages.tool_runner`) automates the
extract → execute → resend cycle internally, which is normally preferred. This change's
requirements (Tool Use Extraction and Execution, Tool Dispatcher and Unknown Tool Handling, Safety
Iteration Cap) call for explicit, inspectable control over that cycle — extracting `tool_use`
blocks, appending assistant/tool_result messages, and counting iterations against
`MAX_ITERATIONS` are all directly observable behavior the test must assert on. The Tool Runner
hides these steps and is still beta. A manual `while` loop around `client.messages.create()`
(the pattern documented for exactly this use case) satisfies the requirements without a beta
dependency.

**2. Package layout.**
```
agent_loop/
  __init__.py
  tools.py       # tool definitions (name/description/input_schema), calculator + web_search
                 # implementations, and the dispatcher
  loop.py        # run_agent_loop(): the manual loop, MAX_ITERATIONS, stop_reason handling
  test_agent_loop.py   # pytest test(s), incl. the multi-step lifecycle test
  requirements.txt     # anthropic, pytest
  README.md      # how to run the loop and the test
```
Kept flat (no subpackages) — three small modules is proportionate to two tools and one loop
function; splitting further would be premature structure for this size.

**3. `calculator` uses a restricted expression evaluator, not `eval()`.**
`eval()` on a string that ultimately originates from model output is a code-injection risk.
`calculator` SHALL parse the `expression` with `ast.parse(..., mode="eval")` and evaluate only a
whitelist of node types (numeric literals, `+ - * / ** ()`, unary +/-); any other node (names,
calls, attributes, subscripts, comprehensions, etc.) is rejected and returned as a `tool_result`
with `is_error: true` rather than raising an unhandled exception into the loop.

**4. `web_search` is a stub keyed on the query, not a live call.**
Per the spec, `web_search` SHALL NOT make a network request. It returns a small canned string for
recognized queries (e.g. a query containing "france" and "population" → a France-population
result matching the worked example) and a generic "no results" stub for anything else, so the
tool always returns *some* string result and the loop's tool_result contract is never empty.

**5. Testing strategy: mock the Anthropic client's `messages.create`, not the network.**
The multi-step lifecycle test monkeypatches (`unittest.mock`) the object the loop calls —
`client.messages.create` — to return three scripted, minimal stand-ins for `Message` (only the
attributes the loop code reads: `content` blocks with `.type`/`.name`/`.input`/`.id`/`.text`, and
`.stop_reason`), reproducing web_search → calculator → end_turn in order. This keeps the test
deterministic, offline, and free of any dependency on `ANTHROPIC_API_KEY`, while still exercising
the real loop, dispatcher, and tool implementations end to end. The test asserts on the tool names
requested, the `calculator` input actually sent (it must incorporate the numeric value the mocked
`web_search` result returned), the `tool_use_id` pairing in the appended `tool_result` blocks, and
the final `stop_reason`/text — never on Claude's exact wording, per the proposal.

**6. Model and credentials.**
`loop.py` defines `MODEL = "claude-haiku-4-5-20251001"` as a module-level constant (overridable
by callers) — tool selection between two unambiguous, well-described tools doesn't need a
frontier-tier model, and Haiku 4.5 is cheaper and faster for this demo;
the Anthropic client is constructed with no explicit key (`anthropic.Anthropic()`), relying on the
SDK's standard `ANTHROPIC_API_KEY` resolution. Only a real, non-mocked run of the loop (e.g. via
the documented `__main__`/README example) needs a credential — the test suite does not, since it
never constructs a live client call.

**7. Logging.**
The `MAX_ITERATIONS`-reached warning uses the standard library `logging` module
(`logging.getLogger(__name__).warning(...)`) — no new logging dependency, consistent with a small
example package.

## Risks / Trade-offs

- **Mocked response shape could drift from the real SDK's `Message`/content-block classes** →
  Mitigation: the mocks only need to supply the attributes the loop code actually reads (documented
  in Decision 5); keep `loop.py` from touching any other attribute so the surface staying accurate
  is easy to review.
- **Restricted AST evaluator still has edge cases (e.g. division by zero, huge exponents)** →
  Mitigation: `calculator` catches evaluation errors and returns them as `is_error: true` tool
  results rather than letting them propagate and crash the loop.
- **Fixed `MAX_ITERATIONS = 20` could cut off a legitimate longer tool chain** → Accepted: the spec
  requires this to be a guardrail only, and normal requests (including the two-tool worked example)
  finish in 3 iterations.

## Migration Plan

Purely additive: a new top-level directory with no interaction with existing code, migrations, or
runtime configuration. No rollback beyond removing `agent_loop/` if the change were reverted.
