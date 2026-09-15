## Why

Nothing in this repository exercises the agentic loop lifecycle - the cycle in which a model
decides to use a tool, the tool runs, its result re-enters the conversation, and the model
decides again with that result in hand. Issue #42 asks for that lifecycle as a standalone,
runnable capability, because the way a loop decides it is finished is the part that is most
often got wrong: completion is inferred from the shape or wording of a response instead of read
from the signal the model already provides.

## What Changes

- Add an agent loop that gives a model two tools, executes whichever it requests, returns the
  result, and continues until the model reports it has finished.
- Add a `calculator` tool that evaluates an arithmetic expression, and a `web_search` tool that
  returns stub results for a query.
- Decide termination **solely** from the model's reported stop reason. Neither the type of the
  first content block, nor any phrase in the response text, nor a fixed number of turns may end
  the loop normally.
- Support a task needing several tool calls in sequence, where a value obtained from one tool is
  used by the next.
- Add a safety cap of 20 iterations. Reaching it logs a warning and fails loudly; a caller cannot
  receive a capped run as though it had completed.
- Report an unrecognised stop reason, or a tool request carrying no tool to run, rather than
  treating either as a normal ending.

## Capabilities

### New Capabilities

- `multi-tool-agent-loop`: the agentic loop lifecycle - tool registration, model-driven tool
  selection, tool execution, result threading, stop-reason-driven termination, and the iteration
  safety cap.

### Modified Capabilities

(none - this capability stands alone and changes no existing behaviour)

## Impact

- New top-level `agent_loop/` package with its own dependency list, independent of the Django
  project. Nothing under `sdd_django_demo/` changes, and its test suite is unaffected.
- New dependency: the Anthropic SDK, scoped to this package only.
- Tests run without any credential and cover every requirement except model tool selection, which
  needs a live model. That one test runs when `ANTHROPIC_API_KEY` is present; when it is absent
  the suite still passes but reports the requirement as unverified rather than skipping silently.
- No CI secret is added, and no continuous integration workflow changes.
