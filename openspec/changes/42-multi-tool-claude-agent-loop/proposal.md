## Why

Every feature built so far in this repo is a Django REST endpoint whose behaviour is specified
and then generated. There is no worked example yet of the other shape of agentic work this repo
teaches: a client-side loop that lets Claude choose between multiple tools, executes them, and
keeps going until the model itself signals it is done. Issue #42 asks for exactly that as a
standalone exercise - a calculator and a stub web-search tool, wired into a loop around the
Messages API - so learners practise reading `stop_reason` as the sole termination signal rather
than a completion mechanism they infer from response content.

## What Changes

- Add a new, Django-independent Python package that defines two tools (`calculator`,
  `web_search`) with JSON Schema `input_schema` definitions, and a loop that calls Claude, acts
  on `tool_use` by executing the matching tool and feeding the result back, and terminates only
  on `stop_reason == "end_turn"`.
- `web_search` is registered as Anthropic's provider-executed server tool
  (`web_search_20260209`, `max_uses: 3`); Anthropic's servers perform the real search - this code
  implements no search logic, mock or otherwise. (Supersedes the original stub decision, per the
  PR #43 review request from the repo owner.)
- `calculator` evaluates a numeric expression string and returns the result; it does not use an
  unrestricted `eval`.
- A hard-coded `MAX_ITERATIONS = 20` guardrail stops the loop and logs a warning if reached; it
  is never the normal way a run ends.
- A test exercising the full multi-step lifecycle from the issue (search for France's
  population, then calculate 10% of it) against the real Claude API, asserting the loop visits
  `web_search`, then `calculator`, then ends via `end_turn` with the correct figure in the final
  text.

## Capabilities

### New Capabilities
- `multi-tool-agent-loop`: a loop that sends a conversation to Claude with a calculator and a
  web-search tool available, executes whichever tool Claude requests, feeds the result back, and
  returns Claude's final answer once it signals `end_turn` - supporting any number of sequential
  tool calls up to a fixed safety cap.

### Modified Capabilities
(none - this does not touch the signup/signin/embargo/password-reset capabilities or their
specs)

## Impact

- New top-level directory at the repo root, sibling to `sdd_django_demo/` (not a Django app,
  no Django/DRF dependency) - this capability has no HTTP surface and nothing for the existing
  project's URLs, settings, or ORM to know about.
- New dependency: the `anthropic` Python SDK (Messages API, tool use).
- New environment variable, `ANTHROPIC_API_KEY`, required to run the loop and its test - the
  first place in this repo where running the test suite needs one, since the acceptance test
  calls the live API rather than a stub.
- No changes to `sdd_django_demo/`, its specs, or its tests.
- `web_search` test coverage can no longer run fully offline against a mock the way it
  originally could; unit tests exercise the new `server_tool_use` event handling via a scripted
  fake response instead, and the live acceptance test now depends on a real web search result
  rather than a fixed stub string.
