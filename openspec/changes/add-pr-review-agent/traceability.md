# Traceability: PR Review Agent

One row per requirement in [`specs/pr-review/spec.md`](./specs/pr-review/spec.md). Code and test
paths are relative to `tooling/pr-review/` unless stated otherwise. This change was delivered in
three phases (see `tasks.md`); rows were added to this table as each phase landed, not before - a
row for unimplemented behaviour would be a requirement with no code, which is exactly the gap
this file exists to catch. All phases are now complete.

| Requirement | Code | Test |
|---|---|---|
| Post each finding as its own isolated comment | `review/publish.py:post_review`, `format_comment` | `test_publish.py::test_inline_attachable_finding_is_posted_as_part_of_one_review`, `test_near_duplicate_findings_produce_only_one_comment` |
| Fall back to a general comment for unattachable findings | `review/publish.py:partition`, `post_general_comment` | `test_publish.py::test_unattachable_finding_becomes_its_own_general_comment` |
| Suppress duplicate findings | `review/dedupe.py:collapse_duplicates`/`find_match`, `review/publish.py:run` (dedupe before the already-posted check, which combines an exact fingerprint match with `find_match` against parsed existing comments - see Notes) | `test_dedupe.py` (all), `test_publish.py::test_already_posted_finding_is_not_reposted`, `test_nothing_to_post_when_all_findings_are_already_posted`, `test_near_duplicate_findings_produce_only_one_comment`, `test_collapsed_duplicates_losing_side_is_not_reposted_on_a_later_run`, `test_reworded_finding_from_an_independent_run_is_not_reposted` |
| Never disclose secret values in a finding | `review/secrets_scan.py:redact`, `review/publish.py:redact_findings` | `test_secrets_scan.py` (all), `test_publish.py::test_secret_value_in_a_finding_is_redacted_before_posting` |
| Run deterministic lint checks on every pull request | `.github/workflows/ruff.yml` (the `ruff` job; final step fails the check based on Ruff's real exit code) | No pytest test - a workflow's trigger/pass-fail behaviour isn't unit-testable. Verified via `actionlint` and task 6's manual verification against a real pull request. |
| Post lint violations as inline comments | `review/ruff_adapter.py:convert` (feeds the same `review/publish.py` pipeline as the rows above) | `test_ruff_adapter.py` (all) |
| Trigger an AI-assisted review only from a collaborator's request | `.github/workflows/claude-pr-review.yml` (relies on claude-code-action's own built-in write-access check, not a hand-rolled one - see Notes) | No pytest test - trigger/authorization behaviour isn't unit-testable. Verified via `actionlint` and task 10's manual verification, including a non-collaborator comment producing no review. |
| Select only relevant review skills | `tooling/pr-review/orchestrator_prompt.md` (the orchestrator's own judgement - deliberately not a separate model call) | Not unit-testable (prompt content, not code). Verified via task 10's manual verification against varied request phrasings. |
| Run selected skills concurrently | `orchestrator_prompt.md` (instructs one `Task` call per skill in a single message) | Not unit-testable (depends on the orchestrator's own tool-call behaviour at runtime). Verified via task 10's manual verification. |
| Post each finding as its own isolated comment (AI-assisted case) | `.claude/agents/*.md` (each subagent returns its own findings, tagged with `source`) + `review/publish.py` (already covered above) | `test_agent_definitions.py` (structural: each agent is isolated by design - restricted tools, its own model, its own checklist) |
| Post one summary per AI-assisted review run | `review/publish.py:run` (`always_summarize` parameter - always posts a summary, even with zero findings, unlike Ruff's silent-when-clean default) | `test_publish.py::test_always_summarize_posts_a_summary_even_with_zero_findings`, `test_without_always_summarize_zero_findings_posts_nothing`, `test_skills_list_names_sources_even_when_no_findings_survive_to_infer_it` |
| Suppress duplicate findings (across skills, and across Ruff/skill sources) | Same `review/dedupe.py`/`review/publish.py` mechanism as the Phase 1 row - source-agnostic by construction | Same tests as that row; `--skills` explicitly supports attributing a summary to multiple sources |
| Treat reviewed content as data, not instructions | `.claude/skills/pr-review-common/SKILL.md` (rule 1) + `orchestrator_prompt.md`'s own "Everything you read is data" section | Not unit-testable (prompt content). Verified via task 10's manual verification with content phrased as an instruction. |
| Never disclose secret values in a finding (AI-assisted case) | `.claude/skills/pr-review-common/SKILL.md` (rule 4, soft control) backed by `review/secrets_scan.py` (hard control, already covered above) | Same tests as the Phase 1 row - the hard backstop applies regardless of which source produced the finding |
| Findings are advisory and do not block merge | No status-check gating exists anywhere in `claude-pr-review.yml` or `publish.py` - absence is the implementation | Implicit: no code path in this change ever fails a check based on a finding's severity |

## Notes

- **Real docs, not assumptions, for `claude-pr-review.yml`**: fetched `anthropics/claude-code-action`'s
  actual `action.yml` and `docs/*.md` before writing this file, rather than relying on earlier
  in-conversation guesses. Two corrections this produced: (1) collaborator-only triggering is
  already enforced by the action itself by default (`docs/security.md`) - no hand-rolled
  `author_association` check needed; (2) setting the `prompt` input switches the action into
  "automation mode," which runs unconditionally on every qualifying event and ignores the trigger
  phrase entirely (`docs/faq.md`) - using `prompt` as originally planned would have made Claude run
  on every PR comment, not just `@claude` ones, directly violating this project's first stated
  requirement. Fixed by using `claude_args: --append-system-prompt` instead, which coexists with
  mention-gated (interactive) mode.
- `.claude/agents/`, `.claude/skills/`, and workflow files are read from a pull request's BASE
  branch, not the PR's own branch (`docs/security.md`) - confirmed via the same real-docs check.
  This is a security property (a PR cannot smuggle in different review behaviour for itself), but
  it also means Phase 3 must exist on whatever branch a manual-verification PR targets, not
  necessarily `main` - see `tasks.md` task 8.3.
- `review/diff.py:valid_positions` and `PullRequestContext` underpin both of the covered rows
  above (an inline comment is only possible where a position is valid; everything else is the
  fallback) but has no requirement of its own in the spec - it is infrastructure the two rows
  above depend on, exercised directly by `test_diff.py`.
- Every row has at least one test or an explicit note on why it has none (workflow trigger/
  authorization behaviour, prompt content, and "absence of a code path" are not unit-testable);
  every test in `review/tests/` serves at least one row above or is infrastructure-level
  (`test_diff.py`, `test_agent_definitions.py`). No orphans in either direction.
- **Bug found during manual verification** (task 3.1, real PR #3 on `ibtisam-saeed/ai-on-boarding`):
  `run()` originally checked each candidate's fingerprint against already-posted comments *before*
  deduping. A collapsed duplicate's losing side is never individually posted, so its own
  fingerprint was never recorded - only the survivor's was. On a second run with the same input,
  the loser passed the "already posted" check (it had never been posted under its own identity)
  and was posted fresh, as if new. Fixed by deduping first, then checking the survivor's
  fingerprint - see `test_collapsed_duplicates_losing_side_is_not_reposted_on_a_later_run`, which
  reproduces the exact scenario and was confirmed red against the original ordering before the fix.
- **Scope correction found while setting up Phase 2's manual verification** (task 6): the first
  version of `ruff.yml` ran `ruff check sdd_django_demo` unscoped - since this repo already has 14
  pre-existing violations, every PR (regardless of what it touched) would have produced roughly
  10 fallback general comments about unrelated code. Fixed by scoping Ruff to the PR's actual
  changed Python files (via `gh pr diff --name-only`) before running it, so `publish.py`'s
  fallback path is only ever exercised for its intended case - a touched file, an untouched line -
  not "file the PR never touched at all."
- **Bug found during Phase 3's real manual verification** (task 10.3/10.4, real PR #5 on
  `ibtisam-saeed/ai-on-boarding`): a second `@claude review this` with no code change reposted all
  four findings instead of recognising them as already posted. Cause: `collect_existing_fingerprints`
  only matched an *exact* fingerprint (`file|line|category|title`), which works for deterministic
  sources (hand-written JSON, Ruff) but not for LLM-generated findings - an independent subagent
  call reviewing unchanged code reworded its titles slightly (e.g. "Hardcoded API key literal
  committed as a module-level constant" became "Hardcoded API key committed as a module-level
  constant" on the second run), so the exact hash never matched. Confirmed via `difflib`
  similarity on the real observed title pairs (0.93, 0.73, 0.68, 0.67 - all comfortably above the
  existing 0.6 dedupe threshold) that the fix didn't need a new threshold, only a new comparison:
  fixed by adding `dedupe.find_match` (reusing `collapse_duplicates`'s same location+similarity
  heuristic) and running it against pseudo-findings reconstructed from existing comment bodies
  (`publish.py:collect_existing`), in addition to - not instead of - the exact fingerprint check.
  `format_comment` now embeds `_Location: {file}:{line}` in every comment (previously only
  inferable for inline comments via GitHub's own `path`/`line` fields, never recoverable at all
  for fallback comments) so this reconstruction works for both. See
  `test_reworded_finding_from_an_independent_run_is_not_reposted`, which uses the real observed
  title wording from PR #5 and was confirmed red against fingerprint-only matching before the fix.
- **Second, structural finding from the same real PR #5 run**: a subsequent `@claude review this
  PR` posted nothing at all - not even the always-on summary. The run's logged SDK options showed
  the actual `allowedTools` granted was `[Glob, Grep, LS, Read, mcp__github_comment__
  update_claude_comment, mcp__github_ci__*, Bash(git add/commit/push/rm), Task,
  Bash(python -m review.publish:*)]` - claude-code-action MERGES `--allowedTools` with its own
  platform defaults rather than replacing them, so the orchestrator's real tool list included git
  write access and its own tracking-comment editor, neither of which `claude-pr-review.yml`
  granted deliberately. The result also reported `"permission_denials_count": 6` with real cost
  and 19 turns spent, never reaching `publish.py`: `orchestrator_prompt.md` step 1 instructed
  `gh pr diff <n> --name-only` to find changed files, but the workflow never granted `gh` access
  at all - only `Bash(python -m review.publish:*)`. Fixed by adding
  `Bash(gh pr diff:*)` (read-only) to `claude-pr-review.yml`'s `--allowedTools`, and by adding an
  explicit "do not use the git-write or comment-editing tools, even though you may have them"
  instruction to `orchestrator_prompt.md`, since - unlike subagent tool restriction, which is a
  separate, independently-enforced mechanism via each agent's own `tools:` frontmatter and is
  unaffected by this - the orchestrator's own restriction is a prompted convention here, not a
  structural guarantee. Worth being explicit that this is a real, if narrow, gap relative to how
  the design was described before this run: see the header comment in `claude-pr-review.yml` for
  the corrected description.
- **Third bug from real Phase 3 verification, PR #11 on `ibtisam-saeed/ai-on-boarding`**: a
  `@claude review this PR` run left only claude-code-action's own generic tracking comment ("I'll
  analyze this and get back to you") - no findings, no summary. Diagnosed from the unredacted job
  log (`show_full_output: true`, run `34642254814`, still enabled from the PR #5 investigation
  above): `orchestrator_prompt.md` step 3 dispatches all selected skills via `Task` in one
  message, and step 4 was written as if each subagent's result comes back synchronously from that
  call. In the real run, all three subagents (`security-review`, `architecture-review`,
  `code-quality`) executed as background tasks whose results arrived as separate notifications
  across later turns - matching Claude Code's own fork/background-task model, not a single
  blocking exchange. The orchestrator correctly logged each arrival ("Security review is in...
  still waiting on architecture and code-quality", then "...still waiting on code-quality"), but
  its final turn repeated "waiting on code-quality" after code-quality's result had already
  arrived (confirmed from log timestamps: the `task_notification` for code-quality preceded that
  message), then made no further tool call. The session ended there (`num_turns: 7`, `is_error:
  false`, `subtype: success` - a clean exit, not a crash or turn-limit error) without ever
  reaching step 4's JSON extraction or step 5's `publish.py` invocation, even though every
  subagent had, in fact, already finished. Fixed by adding an explicit "track dispatched skills
  across turns" note to step 3 and a hard rule at the top of step 4: the instant every dispatched
  skill has reported, proceed through steps 4-5 in that same turn rather than ending it with a
  status update, and re-check the dispatch list against received results before writing any
  "still waiting" message (a stale reference to an already-reported skill is the tell that one
  was missed). Not yet re-verified against a real trigger - see tasks.md task 10.3.
  Plausibly the same root cause as the still-unresolved "missing `_Location:` line" bug above (a
  run cut off mid-collection may have posted something outside the normal step-5 path rather than
  failing silently the way PR #11 did) - not separately confirmed either way. `show_full_output`
  has since been reverted (`claude-pr-review.yml`) now that the async-collection bug it was
  enabled to investigate is fixed and verified; the original "missing `_Location:` line" report
  itself was never independently reproduced or diagnosed, and stays an open, undiagnosed report
  rather than a closed bug - worth re-enabling `show_full_output` temporarily again if it
  resurfaces.
- **Fourth bug from real Phase 3 verification, PR #11 on `ibtisam-saeed/ai-on-boarding`**: after
  the async-collection fix above was merged and re-triggered twice on the same, unchanged PR, the
  first run posted 5 findings correctly; the second run correctly recognised 2 of 4 candidates as
  already-posted but reposted the other 2 as new. Both reposted findings were reworded/re-scoped
  versions of architecture-review findings from the first run at the same location: "Raw SQL
  cursor bypasses the ORM layer this project standardises on" vs. "Hand-written SQL data access
  bypasses the ORM pattern used throughout this project" (title similarity 0.568), and "Debug
  scratch module added to the application package with no backing spec or change" vs.
  "Review-tooling scratch fixture added to the Django application package, duplicating an
  existing fixture" (0.610 - the second run's architecture-review subagent had consolidated two
  of the first run's separate findings into one). Both fell at or below the existing
  `dedupe.TITLE_SIMILARITY_THRESHOLD` of 0.6 - exactly the risk `design.md`'s "Risks" entry on
  this heuristic flagged as needing validation against real examples, confirmed here with real
  production pairs rather than curated fixtures. Fixed by lowering the threshold to `0.5`
  (`review/dedupe.py`), chosen for real margin on both sides: it sits below `test_dedupe.py`'s
  existing "distinct titles" (0.208) and "very differently worded duplicate" (0.320) fixtures,
  which must stay unmatched, while clearing both real pairs above. Added
  `test_real_reworded_pair_from_pr11_is_recognised_as_duplicate` and
  `test_real_rescoped_pair_from_pr11_is_recognised_as_duplicate` to `test_dedupe.py`, using the
  exact real titles, exercising both `collapse_duplicates` and `find_match` directly; full suite
  (37 tests) passes. **Not yet re-verified against a real trigger** - per-run cost (~$0.65-0.70,
  ~4 points of the account's 5-hour usage window each) means further `@claude` triggers on this
  PR are deliberately paused until there is a specific reason to run one; see tasks.md task 10.4.
- **Fifth bug, and a failed first fix attempt at the third bug above**: re-triggering `@claude`
  after that third-bug fix landed on `main` reproduced the exact same symptom - only
  claude-code-action's generic tracking comment, `publish.py` never invoked (`Bash(gh pr
  diff:*)` ran once; no `python -m review.publish` call anywhere in the log; `num_turns: 7`,
  clean `success`). Diagnosed by correlating each background `Task` dispatch's `task_id`/
  `tool_use_id` back to its `subagent_type` to get the true notification order:
  `security-review` (10:23:56) -> `code-quality` (10:24:16.85) -> `architecture-review`
  (10:24:17.79, the actually-last notification). The orchestrator's final turn (10:24:18.29,
  right after that last notification) read: "Code-quality agent completed. Still waiting on
  architecture-review." - misattributing the just-arrived result to the wrong skill and
  wrongly believing one was still outstanding, then making no further tool call. This shows the
  third bug's fix (instructing the orchestrator to "recheck your dispatch list before writing a
  status message") was insufficient in practice: the failure isn't a missing instruction, it's
  the orchestrator's own running narrative about which skills have reported drifting from the
  actual transcript, and trusting that narrative instead of re-deriving the count. Fixed by
  rewriting step 4's opening to require re-counting from the actual subagent messages in the
  transcript on every turn, not from the orchestrator's own prior status text, with an explicit
  warning against the exact failure mode observed (misattributing which notification just
  arrived). **Not yet re-verified against a real trigger** - this is now the second attempt at
  fixing this class of bug; if a third attempt is needed, the async background-dispatch model
  itself (step 3's "one `Task` call per skill in a single message") should be reconsidered against
  the spec's "run selected skills concurrently" requirement - e.g. dispatching sequentially would
  mean at most one outstanding result at a time, structurally eliminating the multi-notification
  attribution race this bug and the third bug both stem from, at the cost of no longer running
  skills concurrently.
- **Sixth bug: the fifth bug's fix worked, exposing a second failed fix attempt at the third
  bug (dedupe)**: re-triggering `@claude` after the fifth-bug fix landed confirmed
  `publish.py` was finally reached correctly on the first try, but 2 of the 3 findings it posted
  were, again, reworded duplicates of already-posted findings (raw-SQL-bypasses-ORM at line 25,
  and the scratch-module/duplicated-fixture finding at line 1) - only 2 of the 4 real candidates
  were recognised as already-posted. This is a *third* independent architecture-review wording of
  each: measuring title similarity across all three real wordings of the raw-SQL finding gave
  0.568 (run 1 vs run 2), 0.386 (run 2 vs run 3), and 0.507 (run 1 vs run 3, only just above the
  0.5 threshold from the third bug's fix) - no single fixed cutoff reliably separates this
  cluster from the "distinct titles" (0.208) and "known limitation" (0.320) fixtures, because each
  independent rewording drifts a different, unpredictable amount from every prior one. Character-
  similarity threshold-tuning was the wrong kind of fix, not just miscalibrated (a second explored
  alternative, comparing full explanation text instead of title, was *worse*: the same real
  explanation pairs scored 0.056-0.071, since long free-form LLM prose shares almost no exact
  character runs even when describing the identical code path). Fixed by changing `find_match`
  (the cross-run already-posted check only, not `collapse_duplicates`'s within-run dedup) to treat
  same-location-and-same-category as sufficient on its own, keeping title similarity only as an
  additional path for a same-titled cross-category match. Rationale: an independent subsequent run
  reporting from the same skill at the same location on unchanged code is reliably the same
  underlying point, regardless of wording, while two genuinely distinct concerns from one skill at
  nearby lines *within a single run* (the case `collapse_duplicates` still guards, unchanged) is a
  real, separate scenario worth preserving. Added
  `test_real_third_rewording_from_pr11_is_recognised_via_category_not_title` and
  `test_find_match_still_respects_category_for_cross_category_low_similarity` to `test_dedupe.py`;
  full suite (39 tests) passes. **Not yet re-verified against a real trigger.**
- **Seventh bug: the sixth bug's fix worked, but a fourth real trigger drifted on a different
  axis - location, not title**: re-triggering after the sixth-bug fix landed confirmed the
  category-based match works (the security and code-quality candidates were correctly recognised
  as already-posted), but a fourth independent wording of the raw-SQL finding was anchored to line
  20 (the `def get_user_orders(user_id):` line) instead of line 25 (the `cursor.execute(...)` call
  inside it) that all three prior runs had used - a 5-line drift for the identical function-level
  issue. `find_match`'s location gate (`LINE_WINDOW = 3`) rejected the pair before category
  matching ever ran, so the sixth bug's fix never got a chance to apply. Unlike title wording,
  this drift is bounded, not open-ended: the function's physical span in an unchanged file cannot
  grow between runs. Fixed by widening `LINE_WINDOW` from 3 to 8 - real margin over the observed
  5-line spread for a small function - safe against over-merging because the sixth bug's
  category-gating already does the discriminating work for `find_match`, so a wider window mostly
  just gives category-matching more candidates to correctly accept or reject, rather than
  reintroducing false positives. Added
  `test_real_fourth_rewording_from_pr11_anchored_to_a_different_line_in_the_same_function` to
  `test_dedupe.py`; full suite (40 tests) passes. **Not yet re-verified against a real trigger.**
  Four real triggers in a row have each surfaced a genuine, previously-unseen bug (permission
  scope, dedupe threshold, async bookkeeping, dedupe category, dedupe location) - worth treating
  as a signal in its own right: if a fifth trigger surfaces yet another independent-axis drift in
  this same matching logic, that is the point to stop patching individual axes and reconsider the
  matching rule's shape itself (e.g. anchoring on the subagent-reported enclosing function/symbol
  name, which is stable across runs on unchanged code, rather than a raw line number), not add a
  sixth heuristic tweak.
- **Eighth bug: not a fifth drift axis after all, but a real defect in the sixth bug's own fix**.
  A fifth real trigger posted two architecture findings that were, again, already-posted
  duplicates (the scratch-module/duplicated-fixture concern, now a fourth and fifth independent
  wording). Investigated by pulling the PR's actual comment bodies directly (`gh api
  .../pulls/11/comments`) rather than retriggering again. Root cause: `_parse_posted_finding`
  (which reconstructs an "already posted" pseudo-`Finding` from a comment's body, for
  `find_match` to compare against) has always hardcoded `category="code-quality"` - harmless
  while `find_match` only compared titles, but the sixth bug's fix added
  `candidate.category == other.category` as a match path without updating this reconstruction, so
  `other.category` was *never* a finding's real category unless that real category also happened
  to be "code-quality". Every already-posted architecture finding therefore compared as category
  "code-quality", not "architecture", so the category path silently never fired for
  architecture (or security, or optimization) findings at all - it happened to look like it was
  working in the sixth and seventh bugs' verification runs only because those specific titles
  still cleared the similarity threshold by coincidence. Fixed by parsing the real source from the
  comment's `_Source: {source}_` line (`format_comment` always includes it) and mapping it to a
  category via a fixed table (`SOURCE_TO_CATEGORY` in `review/publish.py`, mirroring
  `orchestrator_prompt.md`'s skill table), instead of a hardcoded placeholder. Added
  `test_category_recovered_from_posted_comment_matches_far_reworded_title` to `test_publish.py`,
  using two real title wordings (similarity 0.347, confirmed red without the fix, reproducing the
  exact observed symptom, then green with it); full suite (41 tests) passes. **Not yet
  re-verified against a real trigger.** This was caught without spending on another live trigger -
  pulling the actual posted comment bodies via `gh api` and reasoning through the matching code
  directly was enough; worth doing that first before assuming a new drift axis next time too.
- **Cost optimization from real Phase 3 usage data, not a bug**: real `@claude` run logs (job
  results' `total_cost_usd` and the SDK's `unifiedWindows.five_hour.utilization` deltas) showed
  each trigger costing roughly $0.65-0.70 and ~4 percentage points of the account's 5-hour usage
  window, dominated by two Opus subagent calls (`security-review`, `architecture-review`) per
  run - confirmed from the `claude-opus-5` model tags appearing 15-20 times per run in the job
  logs, versus a handful of Haiku calls for `code-quality`. With no overage allowed on this
  account (`overageStatus: "rejected"`, `overageDisabledReason: "org_level_disabled"`), repeated
  manual-verification triggers were a real, observed constraint on how much testing could be done
  in one session. Moved `security-review` and `architecture-review` from `opus` to `sonnet`
  (`.claude/agents/security-review.md`, `architecture-review.md`, and the corresponding row in
  `orchestrator_prompt.md`'s skill table) - all three non-`code-quality` skills now run on Sonnet.
  This is a quality/cost trade-off, not a correctness fix: it has not been re-validated against
  the golden PR fixture (`review/tests/fixtures/golden_pr_snippet.py`) or a real trigger to confirm
  finding quality holds at the cheaper tier - worth doing before relying on it for anything other
  than cost.
- **`/code-review` finding, blocking**: the hand-rolled retry logic added for the transient-
  GitHub-API-failure improvement above (`diff.py`'s `_request_with_retry`) retried `github_post`
  on the same status-code logic as reads, but comment/review-creation POSTs are not idempotent -
  a 502/503/504 arriving after the write already committed server-side would cause a blind
  re-POST and a duplicate PR comment, which nothing downstream catches (the dedupe/fingerprint
  logic only compares across separate runs, not within one run's own retry). The same review pass
  also found the custom retry only inspected `response.status_code`, so a connection-level failure
  (no `Response` object exists yet) was never retried at all despite the code's own stated
  purpose, and a non-numeric `Retry-After` (an HTTP-date, valid per RFC 9110) would crash with an
  unhandled `ValueError` instead of a clean `GitHubError`. Fixed by replacing the ~50-line custom
  implementation with `urllib3.util.retry.Retry` mounted via `requests.adapters.HTTPAdapter` on a
  module-level `Session` - `allowed_methods` excludes POST by default (eliminating the duplicate-
  comment risk structurally, not just by convention), connection-level failures are retried by
  urllib3 itself (real transport-layer behaviour, not status-code matching), and `Retry-After`
  parsing (including the HTTP-date form) is handled by urllib3's own implementation instead of a
  bare `float()` call. Also added `retry_after_max=60` so a CI job can't sleep through its own
  budget on an unbounded server-supplied wait. Testing this required a real local HTTP server
  (`_ScriptedServer` in `test_diff.py`) rather than monkeypatching `requests.get`/`.post` directly,
  since the retry loop now lives inside urllib3's connection handling, invisible to a mock at that
  level - 8 new tests, including one that specifically proves a POST is never retried regardless
  of status (the exact case the finding was about). Two related nits from the same review pass
  (no logging on retry; the shared error message dropping the GET/POST prefix) were left open -
  not part of this fix. Full suite (48 tests) passes.
