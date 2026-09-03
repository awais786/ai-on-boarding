## 1. Script scaffolding

- [x] 1.1 Create `enhanced_agent_loop.py` (a sibling script to `agent_loop.py`,
  not an edit to it), importable/runnable standalone, and verify
  `python agent_loop/enhanced_agent_loop.py` (no args) prints a usage message rather than
  crashing
- [x] 1.2 Reuse `requirements-agent-loop.txt`'s `anthropic` pin (or add an equivalent one scoped
  to this script) - no new third-party dependency for `web_search`, since it uses
  `urllib.request`/`json` from the standard library per design.md (no new requirements file
  needed - `anthropic` is the only external dependency and it's already covered by
  `requirements-agent-loop.txt`)

## 2. Tools and validation

- [x] 2.1 Implement `calculator(expression)` using the same `ast`-based whitelist evaluator
  approach as `agent_loop.py` (own copy, not an import - see design.md), and verify it by
  evaluating a sample expression directly
- [x] 2.2 Implement `web_search(query)`: GET
  `https://api.duckduckgo.com/?q=<query>&format=json&no_html=1` with a 5s timeout via
  `urllib.request`, return `AbstractText` or the fallback string when empty, and verify by
  calling it directly with a query known to return an abstract
- [x] 2.3 Wrap `web_search`'s request/parse logic in error handling covering `URLError`,
  `TimeoutError`, and `json.JSONDecodeError`, returning a typed error string instead of raising,
  and verify by forcing each failure mode (e.g. an unreachable host, a monkeypatched timeout, a
  monkeypatched non-JSON response) and confirming no exception escapes
- [x] 2.4 Implement `validate_args(name, args)`: returns `None` when `expression`
  (`calculator`)/`query` (`web_search`) is a non-empty string within the length cap (200 chars /
  500 chars per design.md), otherwise returns an error string; wire `dispatch(name, args)` to
  call `validate_args` first and short-circuit with its error string when invalid, and verify by
  calling `dispatch` with a missing, non-string, empty, and oversized argument for each tool

## 3. Loop and few-shot prompting

- [x] 3.1 Implement the agent loop (`ask -> dispatch -> observe -> repeat`, structurally matching
  `agent_loop.py`'s control flow: call the Messages API with both tools registered, execute
  `tool_use` via `dispatch`, feed back `tool_result`, terminate only on `stop_reason == "end_turn"`,
  with a `MAX_ITERATIONS = 20` safety cap), and verify by forcing the cap with a fake client that
  always returns `tool_use`
- [x] 3.2 Add the few-shot example: one user/assistant text message pair demonstrating
  `web_search` -> `calculator` ordering for an ambiguous request, prepended before the real user
  message on every run, and verify by inspecting the constructed `messages` list before the first
  API call
- [x] 3.3 Add the CLI entry point (`python agent_loop/enhanced_agent_loop.py "<prompt>"`) printing the
  running transcript, including an `[action] web_search(...)` line whenever `web_search` runs,
  and verify by running it by hand against the live API with the France-population-divided
  prompt from the review comment

## 4. Tests (after implementation, from the spec)

- [x] 4.1 List every requirement in `specs/enhanced-agent-loop/spec.md` and what a test would
  need to assert, working only from the spec
- [x] 4.2 Write offline tests (no live API key needed) for `web_search`'s happy path, empty-
  abstract fallback, and each error mode (mocking the HTTP call), and for `validate_args`/
  `dispatch` rejecting each malformed-input case from section 2.4
- [x] 4.3 Write a test asserting the few-shot message pair is present and precedes the real user
  message in the constructed conversation
- [x] 4.4 Write the live acceptance test(s) (`pytest.mark.skipif` when `ANTHROPIC_API_KEY` is
  unset, per `agent_loop.py`'s existing pattern): run the France-population-divided-by-1000 prompt
  end-to-end and confirm it completes via `end_turn` with a `web_search` step in the transcript;
  run at least 3 differently-worded ambiguous prompts and confirm `web_search` precedes
  `calculator` in each
- [x] 4.5 Run the offline suite and confirm all tests pass (22 passed, 4 skipped without a key);
  the live suite could not be run in this environment - no `ANTHROPIC_API_KEY` is set here, so
  it stays unverified pending a run with a key
- [x] 4.6 Prove the safety-cap test can actually fail - temporarily widened `max_iterations` to
  `max_iterations * 1000` inside the loop, confirmed
  `test_loop_enforces_max_iterations_safety_cap_and_logs_warning` fails (the scripted client's
  fixed 5-response list runs dry - `IndexError: pop from empty list` - since the cap no longer
  stops the loop at 5), then restored the file and confirmed it matches the pre-edit version byte
  for byte and the suite is green again

## 5. Traceability, review, and issue

- [x] 5.1 Build `traceability.md` (in this change's folder, per convention) mapping every
  requirement in `specs/enhanced-agent-loop/spec.md` to its code and test
- [x] 5.2 Per explicit instruction, this change is tracked as part of PR #43's existing thread,
  not a separate GitHub issue - the standalone issue originally opened for it (issue #49) was
  closed and its content removed
- [x] 5.3 Run `/code-review` and address any finding that cites a requirement, a named failing
  test, or a documented convention (the review scans the full working-tree diff, which right now
  also includes uncommitted changes to the sibling `42-multi-tool-claude-agent-loop` change; its
  two findings - a `pause_turn` stop-reason handling gap and a live-test assertion bug - were
  both in `agent_loop/loop.py`/`tests/test_agent_loop.py`, not this change's files, and were
  fixed and documented in that change's own `traceability.md`; nothing was flagged in
  `enhanced_agent_loop.py` or `tests/test_enhanced_agent_loop.py` itself)
- [x] 5.4 Run `/code-review` again (round 2, verify-only) until it returns `Ready to merge: yes`.
  This pass ran 8 parallel finder angles against the full working-tree diff (both this change and
  the sibling `42-multi-tool-claude-agent-loop` change, both uncommitted at the time). One real,
  spec-citing bug was in this change's own file: `web_search`'s `except (URLError, TimeoutError,
  JSONDecodeError)` tuple missed failure modes (e.g. `UnicodeDecodeError` on a non-UTF-8 body,
  `ConnectionResetError`) that the "web_search never raises... for any failure mode" requirement
  covers - fixed by catching `Exception` broadly at that one boundary, with two new regression
  tests. The remaining real findings (a `pause_turn` handling gap, a live-test assertion bug, a
  tasks.md convention violation) were all in the sibling change's files and fixed there - see its
  own `traceability.md`. Everything else raised (reuse/simplification/efficiency/altitude
  suggestions for this file - e.g. deduplicating `_format_call` against `agent_loop/__main__.py`,
  concurrent dispatch, DuckDuckGo response caching) was a nit under this repo's review contract
  (no requirement/test/convention citation) and consistent with the sibling change's own
  documented decision against similar speculative complexity - not applied.

## 6. Relocate into a shared `agent_loop/` folder

- [x] 6.1 Per repo-owner request: move `enhanced_agent_loop.py` into the plain `agent_loop/`
  folder alongside its sibling `agent_loop.py` - not a package (no `__init__.py`, still no
  import between the two scripts); run as `python agent_loop/enhanced_agent_loop.py "<prompt>"`
  rather than `python -m enhanced_agent_loop`
- [x] 6.2 Rely on the sibling change's `conftest.py` update (`sys.path.insert(0, .../agent_loop)`)
  for `import enhanced_agent_loop` to keep resolving during test collection; verified with
  `pytest tests/test_agent_loop.py tests/test_enhanced_agent_loop.py` (50 passed, 5 skipped) and
  a manual `python agent_loop/enhanced_agent_loop.py` run (prints the usage message)
