## Why

PR #43's second review comment asks for a follow-on exercise that layers three concerns onto the
base agent-loop pattern from issue #42: a real (non-mocked) web search, defensive validation at
the tool-dispatch boundary, and few-shot prompting to make tool-choice ordering reliable. These
sit in three different layers of the system (a tool, a dispatch-boundary guard, and prompt
content) and are worth exercising together as their own worked example, distinct from
`42-multi-tool-claude-agent-loop`'s change (which moved `web_search` to Anthropic's
provider-executed server tool, per this same PR's *first* review comment).

## What Changes

- Add a new, standalone script `agent_loop/enhanced_agent_loop.py`, in the same plain
  `agent_loop/` folder as its sibling `agent_loop.py` (not an edit to it, not a package import -
  they share a folder for tidiness only), implementing its own two tools, dispatch-boundary
  validation, a few-shot example, and a loop.
- `web_search(query)` calls DuckDuckGo's free Instant Answer API
  (`https://api.duckduckgo.com/?q=<query>&format=json&no_html=1`) for a real result, returning
  `AbstractText` or a fallback string when the response has none; it never raises - network,
  timeout, and malformed-response failures are caught and returned as a typed error string.
- `calculator(expression)` evaluates arithmetic (reusing the same safe-eval approach as
  `agent_loop.py`'s calculator, not an unrestricted `eval`).
- `validate_args(name, args)` runs at the dispatch boundary, before either tool executes:
  rejects a non-string, empty, or oversized `expression`/`query` and returns an error string
  instead of calling the real function.
- A few-shot example - one user/assistant message pair demonstrating the correct
  `web_search` -> `calculator` order for an ambiguous request - is inserted before the real user
  message in every conversation this script starts.

## Capabilities

### New Capabilities
- `enhanced-agent-loop`: a second, standalone agent-loop script that adds a real web-search
  tool, dispatch-boundary argument validation, and a few-shot prompting example to the base
  ask -> dispatch -> observe -> repeat pattern, so that malformed tool calls fail safely and
  ambiguous requests reliably resolve `web_search` before `calculator`.

### Modified Capabilities
(none - `multi-tool-agent-loop` and its spec, and `agent_loop.py`'s own file, are untouched by
this change)

## Impact

- New file `agent_loop/enhanced_agent_loop.py`, sibling to `agent_loop.py` in the shared
  `agent_loop/` folder - a separate script, not wired into `agent_loop.py`'s tools/dispatch/loop.
- New outbound network dependency on a real third-party API (`api.duckduckgo.com`) - the first
  tool in this repo that calls a non-Anthropic external service; unlike the Anthropic API calls
  elsewhere, this needs no API key, but does need network access and is subject to DuckDuckGo's
  own availability and rate limits.
- No changes to `sdd_django_demo/`, `agent_loop.py`, or the `multi-tool-agent-loop` spec.
