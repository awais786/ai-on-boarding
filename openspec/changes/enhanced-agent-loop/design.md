## Context

See proposal.md - Why. `agent_loop/enhanced_agent_loop.py` is a second, independent worked
example living alongside `loop.py`/`tools.py` (the `42-multi-tool-claude-agent-loop` capability),
not a modification of them. Nothing here changes `agent_loop/tools.py`, `loop.py`, `__main__.py`,
or their spec.

## Goals / Non-Goals

**Goals:**
- Satisfy every requirement in `specs/enhanced-agent-loop/spec.md`: a real (non-mocked)
  `web_search` via DuckDuckGo, a `validate_args` guard at the dispatch boundary, a one-pair
  few-shot example steering tool order, and a runnable
  `python -m agent_loop.enhanced_agent_loop "<prompt>"` entry point.
- Read top-to-bottom as a single, self-contained script - the point of this exercise is the
  three added layers (tool / validation / prompting), not a reusable package.

**Non-Goals:**
- Reusing or importing `agent_loop/tools.py` or `agent_loop/loop.py`. This script duplicates the
  small pieces of loop/tool-eval structure it needs rather than depending on the sibling
  capability - see Decisions below.
- General DuckDuckGo API coverage (related topics, disambiguation results, images) - only
  `AbstractText` and a fallback string, per the spec.
- Any Django integration, HTTP endpoint, or persistence.

## Decisions

**Single self-contained script, not built on top of `agent_loop/loop.py`/`tools.py`.**
`agent_loop/enhanced_agent_loop.py` defines its own `TOOLS`, `dispatch`, `validate_args`, and loop, including
its own copy of the `ast`-based safe arithmetic evaluator `agent_loop/tools.py` already has.
Alternative considered: import `agent_loop.tools.calculator` and adapt `agent_loop.loop`'s
control flow - rejected, since `agent_loop.loop.run_agent_loop` isn't parameterized for
pluggable tools/dispatch (adding that would be scope creep into the other capability), and
coupling two independently-readable teaching exercises would defeat the point of either one being
self-contained.

**`web_search(query)` uses `urllib.request` (standard library), not a new dependency.** A single
GET to `https://api.duckduckgo.com/?q=<query>&format=json&no_html=1` with an explicit timeout
(5s) needs nothing beyond `urllib.request` and `json`, both in the standard library - adding
`requests` for one call would be an unjustified new dependency. Response handling: parse the JSON
body, return `AbstractText` if non-empty, else the fallback string `"No summary available for
'<query>'."`. Every failure mode - `URLError` (DNS/connection), `TimeoutError`, and
`json.JSONDecodeError` (malformed body) - is caught and turned into a typed error string
(`f"web_search failed ({type(exc).__name__}): {exc}"`), never raised, per the spec's "never
raises" requirement.

**`validate_args(name, args)` returns `None` when valid, an error string when not.** Checked
before `dispatch` calls the real tool:
- `calculator`: `expression` must be a non-empty `str` no longer than 200 characters (matching
  `agent_loop/tools.py`'s own length cap, for consistency between the two exercises' arithmetic
  tools).
- `web_search`: `query` must be a non-empty `str` no longer than 500 characters (search queries
  are naturally longer than arithmetic expressions; 500 is a generous ceiling with no real
  queries anywhere near it).
`dispatch` calls `validate_args` first and returns its error string immediately if not `None`,
never reaching the real `calculator`/`web_search` call - this is what makes the "malformed tool
call produces a validation error, not a crash" acceptance criterion hold unconditionally, not
just for the failure modes `calculator`/`web_search` already happen to guard against internally.

**The few-shot example is one literal user/assistant text turn, not a synthetic tool_use/
tool_result round trip.** The comment asks for "one user/assistant message pair," and the
Messages API requires any assistant `tool_use` block to be followed by a matching `tool_result`
in the next turn - faking a believable round trip would need at least two additional synthetic
messages (a fake `tool_result` for the search, then a second assistant turn for the calculator
call), which is no longer "one pair." Instead, the few-shot pair is plain conversational text: a
user message posing an ambiguous two-step question, and an assistant message stating it will
search first and then calculate - primed as an example of the reasoning pattern, not a literal
tool invocation. This is prepended to every conversation before the real user message.

**Model: `claude-haiku-4-5-20251001`, matching `agent_loop/`'s choice.** The whole point of the
few-shot example is to keep a cheap model reliable at tool-choice ordering without needing a
larger model - if the ordering scenario (tested across 3 phrasings) turns out unreliable on
Haiku even with the few-shot pair, that is grounds to revisit the model choice, not to add more
prompt engineering around a fixed model.

**Reuses the `MAX_ITERATIONS = 20` safety-cap pattern from `agent_loop/loop.py`, even though the
review comment doesn't mention it.** The "completes without crashing" acceptance criterion
implies a termination guarantee; an LLM loop with no iteration cap can hang indefinitely on a
tool-use disagreement, which isn't a crash but defeats "completes." Ties to the same requirement
`agent_loop/loop.py`'s cap ties to, applied here for the same reason.

## Risks / Trade-offs

- **DuckDuckGo's Instant Answer API frequently returns an empty `AbstractText`** (it isn't a
  general web index) → the spec's fallback-string requirement covers this; some prompts in
  manual testing may get a generic "no summary available" result rather than a specific answer -
  an accepted limitation of using a free, no-key API, not a bug.
- **No API key means no explicit rate-limit handling on our side** → covered by the same
  "never raises" requirement: a throttled or unexpected response is caught by the JSON-decode or
  connection-error paths and surfaced as a typed error string, not a crash.
- **A fixed few-shot pair could bias the model's behavior on unrelated prompts** → accepted
  trade-off, since biasing tool-choice order for ambiguous requests is exactly what the
  acceptance criteria ask this script to demonstrate; the pair is kept short and clearly scoped
  to the search-then-calculate pattern.
- **Verifying "reliably triggers web_search before calculator... across at least 3 phrasings"
  needs 3 live Anthropic API calls per run** → each call costs real tokens; per this repo's
  existing practice (see `agent_loop/`'s live-test skip pattern), these live checks should stay
  minimal and separately identifiable so they can be skipped without `ANTHROPIC_API_KEY`, rather
  than folded into the always-on offline suite.
