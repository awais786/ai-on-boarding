**Phased delivery - read before running `/opsx:apply`.** This change is split into three phases
(sections 1-3, 4-6, 7-10). Each phase ends with its own "Manual verification" section, performed
by the user against a real pull request, not something `/opsx:apply` can check off itself. Do
**not** begin the next phase's implementation tasks until the user has confirmed the current
phase's manual verification tasks. When invoking `/opsx:apply` for this change, apply one phase
at a time and stop at the manual verification section - do not chain automatically into the next
phase's implementation tasks in the same run.

## 1. Phase 1 - Publishing core: package and modules

- [x] 1.1 Create the `tooling/pr-review/` package skeleton (`requirements.txt` with `pydantic`,
      `review/__init__.py`) and verify `pip install -r tooling/pr-review/requirements.txt`
      succeeds and `python -c "import review"` works from that directory
- [x] 1.2 Implement `review/schema.py`: `Finding` (category, severity, file, line, title,
      explanation, suggested_fix) and `Findings` pydantic models, plus a `fingerprint(finding)`
      helper, and verify constructing a `Finding` from a sample dict and calling `fingerprint()`
      on it succeeds
- [x] 1.3 Implement `review/diff.py`: fetch a pull request's changed files and patches via the
      GitHub API and compute, per file, the set of valid inline-comment line positions from each
      patch's hunks; verify against a saved sample patch fixture that it returns the expected
      position set
- [x] 1.4 Implement `review/dedupe.py`: cluster findings by (file, line window) and collapse
      near-duplicate titles via a fuzzy match; verify against an in-code fixture containing two
      similar findings and two dissimilar findings at the same location
- [x] 1.5 Implement `review/secrets_scan.py`: a regex-based scan for common credential/secret
      shapes over a finding's text, redacting and flagging matches; verify against sample strings
      that do and do not contain secret-like patterns
- [x] 1.6 Implement `review/publish.py`: read a findings payload, validate each finding against
      `schema.py`, fetch the pull request's existing comments and extract prior fingerprints,
      drop already-fingerprinted findings, dedupe the remainder via `dedupe.py`, run
      `secrets_scan.py` over what remains, resolve each into an inline comment or a fallback
      general comment using `diff.py`'s positions, and post one GitHub review (inline comments +
      summary body) plus any fallback general comments; verify via a CLI entry point that accepts
      a pull request number and a findings JSON file

## 2. Phase 1 - Tests

- [x] 2.1 List the pr-review spec requirements this phase covers (isolated comment posting,
      fallback for unattachable findings, duplicate suppression, no-secrets disclosure)
- [x] 2.2 Write `review/tests/test_diff.py`, `test_dedupe.py` (including curated
      near-duplicate/false-positive fixture pairs), `test_secrets_scan.py`, and `test_publish.py`
      (mocking the GitHub API - payload shape, fallback routing, fingerprint-skip behaviour) from
      that requirement list; verify `pytest tooling/pr-review/review/tests -q` passes
- [x] 2.3 Break one piece of the implementation on purpose (for example, disable the fingerprint
      check), confirm the relevant test goes red, then restore it, and verify the suite is green
      again

## 3. Phase 1 - Manual verification (STOP - confirm before starting Phase 2)

- [x] 3.1 Using a personal GitHub token, manually run `publish.py` against a real, disposable
      test pull request with a hand-written findings JSON file covering an inline-attachable
      finding, a fallback (unattachable) finding, and two findings that should collapse as
      duplicates - to be performed and confirmed by the user, not checked off automatically
      (confirmed against https://github.com/ibtisam-saeed/ai-on-boarding/pull/3)
- [x] 3.2 Confirm: the inline finding lands as a comment on the correct file/line, the fallback
      finding lands as a general pull request comment, the duplicate pair produces only one
      comment, and the summary/review body lists no individual finding text; re-run the same
      command and confirm no new comments are posted (idempotency) - to be confirmed by the user,
      not checked off automatically (confirmed - a cross-run duplicate-fingerprinting bug was
      found and fixed during this check; see traceability.md; re-run after the fix correctly
      reported "Nothing to post - 3 already posted, 1 duplicate(s) collapsed to zero new
      findings.")

## 4. Phase 2 - Ruff CI integration

- [x] 4.1 Add a Ruff configuration scoped to `sdd_django_demo/` (the only Python application code
      in this repo) and verify `ruff check sdd_django_demo` runs and reports a result
      (`sdd_django_demo/ruff.toml`; migrations excluded; calibrated against the real codebase -
      14 violations, 3 safely auto-fixable, with Ruff's own default rule set)
- [x] 4.2 Implement `review/ruff_adapter.py`: convert `ruff check --output-format json` output
      into `Finding` objects (category `code-quality`, source `ruff`), skipping any violation
      marked safely auto-fixable; verify against a sample Ruff JSON fixture containing both
      autofixable and non-autofixable violations
- [x] 4.3 Add `.github/workflows/ruff.yml`: on `pull_request`, install dependencies, run
      `ruff check --output-format json`, run `ruff_adapter.py`, then call `publish.py` with the
      result; grant the workflow's token `pull-requests: write`; verify the workflow YAML is
      valid and its steps succeed in a local dry run where feasible (also grants `issues: write`,
      needed by `publish.py`'s fallback/summary posting; validated with `actionlint`, and the
      Ruff-to-findings conversion dry-run locally against the real codebase's real violations).
      Scoped to the PR's changed Python files under `sdd_django_demo/` (via
      `gh pr diff --name-only`), not the whole directory - found while setting up task 6's
      manual verification: a whole-directory scan would report this repo's 14 pre-existing
      violations as unattachable (fallback) comments on every PR regardless of what it touches.
      Shell logic (null-delimited `xargs -0`, portable across BSD/GNU) verified locally against
      both an empty and a non-empty changed-files case before relying on it in CI.

## 5. Phase 2 - Tests

- [x] 5.1 List the pr-review spec requirements this phase covers (automatic lint check on every
      pull request, posting non-autofixable violations as inline comments, autofixable
      violations not posted)
- [x] 5.2 Write `review/tests/test_ruff_adapter.py` from that list; verify
      `pytest tooling/pr-review/review/tests -q` still passes
- [x] 5.3 Break the autofixable-skip logic on purpose, confirm the relevant test goes red, then
      restore it, and verify the suite is green again

## 6. Phase 2 - Manual verification (STOP - confirm before starting Phase 3)

- [x] 6.1 Open or update a real test pull request with at least one deliberate non-autofixable
      Ruff violation and one autofixable violation - to be performed and confirmed by the user,
      not checked off automatically (confirmed against
      https://github.com/ibtisam-saeed/ai-on-boarding/pull/4)
- [x] 6.2 Confirm: the Ruff CI check runs automatically and reports the correct pass/fail status,
      an inline comment appears for the non-autofixable violation on the correct line, no comment
      appears for the autofixable violation, and pushing an additional commit without fixing the
      violation does not duplicate the existing comment - to be confirmed by the user, not
      checked off automatically (confirmed - initial run posted exactly 1 inline comment on the
      correct line for RUF012, none for the autofixable I001, and correctly failed the check;
      a re-run with no code change reported "Nothing to post - 1 already posted", confirming
      idempotency; user confirmed the summary comment's content)

## 7. Phase 3 - Skills and subagents

- [x] 7.1 Create `.claude/skills/pr-review-common/SKILL.md`: the content/instruction-separation
      rule, the diff-scope rule, the no-secrets rule, and the required single-trailing-JSON-block
      output format referencing `schema.py`'s `Finding` shape
- [x] 7.2 Create `.claude/skills/security-review-checklist/SKILL.md`,
      `architecture-review-checklist/SKILL.md`, `optimization-checklist/SKILL.md`, and
      `code-quality-checklist/SKILL.md`, each with its rubric (`code-quality-checklist`
      explicitly excluding anything Ruff already covers)
- [x] 7.3 Create `.claude/agents/security-review.md` and `architecture-review.md` (model: opus),
      `optimization.md` (model: sonnet), and `code-quality.md` (model: haiku), each restricted to
      `Read` and `Skill` tools, each instructing the subagent to load `pr-review-common` and its
      own checklist skill by name and apply them to an orchestrator-supplied file list
      (**updated after Phase 3 real-world cost data**: `security-review` and `architecture-review`
      moved from `opus` to `sonnet` - real run logs showed the two Opus subagents were the
      dominant cost driver, ~$0.65-0.70 and ~4 points of the account's 5-hour usage window per
      `@claude` trigger; see traceability.md)
- [x] 7.4 Verify each agent definition file is well-formed (valid frontmatter, references an
      existing skill name) by inspection or a lint script (formalized as
      `test_agent_definitions.py`, not just a one-off check)

## 8. Phase 3 - Orchestrator and trigger

- [x] 8.1 Write `tooling/pr-review/orchestrator_prompt.md`: how to decide which skills apply from
      the requester's comment and the changed files, how to dispatch the relevant subagents in
      parallel, how to extract and validate each subagent's JSON block (retry once on failure),
      and how to invoke `publish.py` with the collected findings
- [x] 8.2 Add `.github/workflows/claude-pr-review.yml`: trigger on `issue_comment` /
      `pull_request_review_comment` containing the trigger phrase, authenticate with
      `CLAUDE_CODE_OAUTH_TOKEN`, and restrict the orchestrator's own tools to
      Read/Grep/Glob/Task plus Bash scoped only to invoking `publish.py`; set a concurrency group
      keyed by pull request number. **Corrected from the original task wording after reading
      claude-code-action's actual docs** (not assumed): collaborator-only triggering does not
      need a hand-rolled `author_association` check - the action enforces write-access-only
      triggering itself by default (docs/security.md). More importantly, the workflow must NOT
      set the `prompt` input - doing so switches the action into "automation mode," which runs
      unconditionally on every qualifying event and ignores the trigger phrase entirely
      (docs/faq.md), which would have violated the "on request only" requirement. Uses
      `claude_args: --append-system-prompt` instead, which points Claude at
      `orchestrator_prompt.md` while keeping mention-gated (interactive) mode intact.
- [x] 8.3 Document, as a task for the user to perform outside of code (not something this list
      can complete automatically), that a repository maintainer needs to generate a Claude Code
      OAuth token (`claude setup-token`) and add it as the `CLAUDE_CODE_OAUTH_TOKEN` repository
      secret before Phase 3 can be exercised. **No GitHub App is required** - by explicit user
      decision, this workflow authenticates to GitHub using only the repository's own default
      `secrets.GITHUB_TOKEN` (passed as `claude-code-action`'s `github_token` input, which the
      action's own docs describe as the supported alternative to a GitHub App, not a workaround),
      the same token `publish.py` already uses. **Required, not previously documented**:
      `.claude/agents/`, `.claude/skills/`, and this workflow are read from the pull request's
      BASE branch specifically (whatever branch the PR targets), not the PR's own branch
      (confirmed via docs/security.md) - so a manual-verification pull request must target a base
      that already has Phase 3 committed to it (e.g. `claude-code-action-pr-reviewer`, once this
      phase is committed there, same as Phases 1-2), not `main`, unless Phase 3 is merged to
      `main` first.

## 9. Phase 3 - Tests

- [x] 9.1 List the pr-review spec requirements this phase covers (collaborator-only triggering,
      skill selection, concurrent execution, isolated findings, summary comment, duplicate
      suppression across sources, content-not-instructions, no-secrets disclosure,
      advisory-only)
- [x] 9.2 Where automatable, write tests from that list - `test_agent_definitions.py` (model
      pinning, tool restriction, skill references - all structurally checkable) and
      `publish.py`'s new `--skills`/`--always-summarize` behaviour the "summary comment" and
      "duplicate suppression across sources" requirements actually depend on; most of this
      phase's behaviour (subagent dispatch, model selection in practice, skill content quality)
      is not unit-testable and is left to task 10's manual verification instead of forcing
      artificial tests around it; verified `pytest tooling/pr-review/review/tests -q` passes
- [x] 9.3 Prepare a small "golden" pull request fixture (a synthetic diff with a planted security
      issue, a planted architecture issue, and a planted style issue) as a documented manual-
      evaluation aid for the checkpoint below, since subagent prompt quality is not unit-testable
      (`review/tests/fixtures/golden_pr_snippet.py` + `golden_pr_README.md`; confirmed the
      fixture itself trips zero Ruff violations, so any finding on it can only come from a skill)

## 10. Phase 3 - Manual verification (final - full end-to-end confirmation)

- [ ] 10.1 Set up the `CLAUDE_CODE_OAUTH_TOKEN` secret per 8.3 - to be performed by the user
- [x] 10.2 On a real test pull request, comment `@claude` from a non-collaborator account (or
      simulate one) and confirm no review starts - to be confirmed by the user, not checked off
      automatically (confirmed 2026-09-12 against PR #11: a comment from a second, non-collaborator
      account produced no review and no posted comments; the workflow run itself fails with
      "Actor does not have write permissions to the repository" rather than silently no-opping -
      expected per claude-code-action's built-in check, design.md Decision 8; costs nothing since
      it's rejected before any Claude session starts - see run 34692737096)
- [ ] 10.3 On the same pull request, comment `@claude` from a collaborator account naming a
      specific concern (e.g. "review for security"), and confirm only the matching skill(s) run,
      inline comments appear isolated per finding and attached to the correct file/line where
      possible, a fallback general comment appears for any unattachable finding, and exactly one
      summary comment/review is posted without repeating finding text - to be confirmed by the
      user, not checked off automatically
- [ ] 10.4 Comment `@claude` again on the same, unfixed pull request and confirm previously
      posted findings are not reposted - to be confirmed by the user, not checked off
      automatically
- [x] 10.5 Confirm Ruff-sourced comments (from Phase 2) and Claude-sourced comments coexist on
      the same pull request without duplicating each other - to be confirmed by the user, not
      checked off automatically (confirmed 2026-09-12 against PR #11: a deliberately planted F841
      violation was posted by Ruff's automatic `pull_request` workflow - `Source: ruff`, comment
      3996181404 - and sits alongside 17+ Claude-sourced comments with no overlap or duplication
      between the two sources; `find_match`'s category recovery correctly maps `ruff` to
      `code-quality` via `SOURCE_TO_CATEGORY`)
- [ ] 10.6 Once all of the above are confirmed, ensure a GitHub issue exists for this change and
      post the proposal and full delta spec to it, per this project's convention - confirm with
      the user before posting, since this writes to a shared, visible location outside the repo
