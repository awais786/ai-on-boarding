# Traceability: add-api-behavior-verification

Maps every requirement in `specs/api-behavior-verification/spec.md` to the code/config that
satisfies it and the test/evidence that verifies it.

| Requirement | Code | Test / Evidence |
|---|---|---|
| Run automatically on every push to main | `.github/workflows/api-behavior-verification.yml` (`on: push: branches: [main]`) | `actionlint` passes on the workflow file (task 7.2); no automated test triggers a real push - verified by config inspection only |
| Derive endpoint coverage from the OpenAPI schema | `postman/generate_collection.js` (converts `schema.json`, produced by `make schema`, via `openapi-to-postmanv2`) | Local run: `schema.json` has 5 paths, `collection.generated.json` has 5 requests, one per path/method - no hand-added endpoint |
| Judge behaviour against the OpenSpec specs | `postman/assertions/*.json` (each entry's `requirement` cites a `### Requirement:` name from `openspec/specs/*/spec.md`) | `postman/lib/merge.js` merge is keyed on `operationId`; `postman/test/merge.test.js` (`node --test`) verifies an entry attaches to its matching request |
| Assert specified behaviour, not just success status codes | `postman/assertions/user-signup.json`, `user-signin.json`, `user-password-reset.json`, `user-password-reset-confirm.json` (field-keyed rejection checks, response-shape checks, not just status) | Local Newman run: e.g. `signup rejects a submission with no email and names the email field` checks the response body, not only the status code |
| Execute checks with Postman tooling | `postman/package.json` (`newman`, `openapi-to-postmanv2`, `postman-collection`), `npm run newman` | Local run: `npm run newman` against `make ci-serve` produced `postman/result.json` with a pass/fail per assertion (30 requests, 40 assertions) |
| Fail the run on an assertion failure | `newman` exits non-zero on any failed assertion (`.github/workflows/api-behavior-verification.yml` step `Run the collection with Newman`) | Task 9.5: deliberately corrupted `Reject a missing email`'s expected status to `999`, confirmed Newman reported it failed (`expected 400 to equal 999`), then restored it and confirmed a clean state again |
| Evaluate coverage and correctness against the specs before passing | `postman/review_with_claude.py` (system prompt requires checking: missing coverage, incorrect assertions, status-only endpoints, live violations) | `postman/test/test_review_with_claude.py` (`python3 test/test_review_with_claude.py`) mocks the model response and exercises the coverage-evaluation contract end to end via `main()` |
| Fail the run on a blocking evaluation finding | `review_with_claude.py::exit_code_for` (non-zero if `ready` is false or any finding is `blocking: true`) | `test_review_with_claude.py::TestExitCodeFor` and `TestMainExitCode` (blocking-finding and ready:false cases both assert a non-zero exit) |
| Non-blocking observation does not fail the run | Same `exit_code_for` (a `blocking: false` finding with `ready: true` is exit 0) | `test_review_with_claude.py::test_nonblocking_finding_with_ready_true_is_zero` |
| Report which requirement failed | Newman's assertion names are the requirement text (set at merge time); `review_with_claude.py::print_verdict` prints each finding's `requirement` field | Task 9.5's Newman failure output names the assertion by its requirement-derived test name; `test_review_with_claude.py` confirms findings carry a `requirement` field through to the verdict |

## Code review

- **Round 1** (`/code-review`): 6 findings. Fixed: (a) a logical contradiction - two assertions
  on the same `signup_create`/`spec_minimal` response asserting mutually exclusive status codes
  (200 vs 400) - by moving "Name the offending field on rejection" to the `missing_email`
  variant; (b) the two drift-affected signup assertions weren't tagged `KNOWN DRIFT` like
  signin's, for consistency with `postman/README.md`; (c) `review_with_claude.py`'s prompt said
  a `KNOWN DRIFT` name is "prefixed" when the actual convention is a suffix, and didn't state
  explicitly that such findings stay blocking; (d) `postman/package.json`'s `npm test` was never
  run in CI - added as a workflow step. Not changed: Newman lacking `continue-on-error` (correct
  per spec - see "Known, documented gaps" below) and a suggested "mark known-drift non-blocking"
  instruction (would contradict the same unconditional requirement).
- **Round 2** (`/code-review`, verify-only): confirmed all 6 round-1 items resolved as claimed,
  and found the identical contradiction pattern reintroduced in
  `postman/assertions/user-signin.json` - "Return HTTP 401 on rejection" targeted `spec_minimal`
  (a request meant to represent an *accepted* submission), contradicting the co-located "Accept a
  signin submission" assertion on the same response. Fixed by moving it to the `missing_password`
  variant (a genuine rejection, already asserting 401 itself - consistent, not redundant in
  effect). Verified locally (not a third agent review pass - the project's review contract caps
  at two): a scan of every assertions file for two entries on the same `(operationId, variant)`
  pair asserting conflicting literal status codes found nothing else, and a live Newman run
  confirms the fixed assertion now passes and the run still shows exactly the expected 5
  `KNOWN DRIFT` failures, no more and no fewer.
- **Verdict: Ready to merge: yes** (round 2's one finding fixed and self-verified per the above;
  everything else round 2 checked was already confirmed correct).

## Post-merge follow-up: signin/signup drift closed, assertions rewritten

The `email_or_username`/`username` drift described below (and the `country`/embargo drift from
the "add-embargo not archived" follow-up above) is now closed: `add-user-signin` was restored
and archived (`openspec/changes/archive/2026-09-01-add-user-signin/`, PR #41), and `add-embargo`/
`add-reset-password-confirmation` were archived with their deltas synced. `openspec/specs/`
now accurately describes what the live API does.

`postman/assertions/user-signup.json` and `user-signin.json` were rewritten accordingly:
- Signup gained real coverage for `username` (missing, format, duplicate, case-normalisation) and
  `country` (missing, blocked) - previously untested.
- Signin, no longer blocked by a field-name mismatch, gained coverage for authentication by email
  and by username (including case-insensitivity), the indistinguishable-rejection guarantee
  (unregistered identifier vs. wrong password, compared via captured collection variables),
  lockout after 3 failures (a 4-request chained fragment: 3 failures then a still-rejected
  correct-password attempt), and the failure-count reset below the lockout threshold.
- `assertions/out_of_scope.json` was updated: the 6 signin entries blocked by the field-name
  drift were removed (now covered for real); "Reject signin for an embargoed account" was added
  (still blocked - no HTTP way to change a country's blocked status between requests); the 3
  `embargo` capability requirements and the 5 confirmation-page requirements (from the
  `add-embargo`/`add-reset-password-confirmation` sync) were added, each with its own rationale.

A full local run after these changes: 50 requests, 61 assertions, **zero failures** - confirmed
via `npm run newman` against `make ci-serve`. `postman/README.md`'s "Known exclusions and known
drift" section was renamed to "Known exclusions" (the drift half no longer applies) and rewritten
accordingly.

## Known, documented gaps (historical - the drift below is now closed, see the follow-up above)

- The live signup/signin endpoints had drifted from `openspec/specs/user-signup/spec.md` and
  `user-signin/spec.md` in ways this change did not introduce and was not scoped to fix (extra
  required fields, `email_or_username` instead of `email`). Five assertions, written strictly
  from the canonical specs, correctly failed against the live API as a result - this was the
  pipeline doing its job, not a defect in it. All five test names carried a `KNOWN
  DRIFT` marker (three signin, two signup - `postman/assertions/user-signin.json`,
  `user-signup.json`) so `review_with_claude.py` and a human reading Newman's output both
  recognized them as already-documented, not newly discovered. See `design.md` "Risks /
  Trade-offs" and the follow-up section above for how this was resolved.
- **These five failures failed the CI job**, on purpose: `specs/api-behavior-verification/
  spec.md`'s "Fail the run on an assertion failure" requirement is unconditional - it does not
  carve out an exception for drift that predates a given push. `/code-review` round 1 flagged
  this as a possible defect ("defeats the pipeline's stated purpose of distinguishing real
  regressions from known drift"); it was not changed, because doing so - e.g. making a `KNOWN
  DRIFT`-tagged Newman failure non-blocking - would directly contradict the spec's own
  unconditional wording and the explicit choice made when this change was proposed (assert
  strictly per the canonical specs rather than the live behaviour, specifically so real drift
  surfaces as a failure instead of passing silently). That prediction held: the drift did surface
  as a failure, and is now fixed at the source (the specs) rather than by weakening this rule.
- `postman/assertions/out_of_scope.json` documents every requirement this pipeline deliberately
  does not check (time-based expiry, true concurrency, outbound-email inspection, database-only
  state, and the non-DRF reset-password HTML page), each with its own rationale, so the Claude
  evaluation step does not mistake a documented boundary for an unintentional coverage gap.
- The Claude evaluation step's live API call itself (`review_with_claude.py` without
  `--dry-run`) was not exercised end-to-end in this implementation session (no
  `ANTHROPIC_API_KEY` / network entitlement available in that environment). Its request-building
  path is verified via `--dry-run` (builds the real ~49KB prompt from the actual specs,
  collection, and result files without calling the API), and its response-handling/exit-code
  logic is verified via `test_review_with_claude.py`'s mocked-response tests. The first real run
  will happen in CI once `ANTHROPIC_API_KEY` is provisioned as a repository secret (see
  proposal.md "Impact").
