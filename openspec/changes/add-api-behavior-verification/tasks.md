## 1. Schema generation

- [x] 1.1 Add a `make schema` target (and/or document the raw command) that runs `manage.py
  spectacular --file schema.json` into `postman/schema.json`, and verify the file is produced and
  is valid JSON containing a path entry for `health`, `signup`, `signin`,
  `password-reset`, and `password-reset/confirm`

## 2. Postman collection generation

- [x] 2.1 Add `postman/package.json` with `openapi-to-postmanv2`, `newman`, and
  `postman-collection` as dependencies, and verify `npm install` inside `postman/` succeeds
- [x] 2.2 Add `postman/generate_collection.js`, converting `postman/schema.json` into
  `postman/collection.generated.json` via `openapi-to-postmanv2`, and verify the output collection
  contains one request per path/method pair in `schema.json`, none hand-added

## 3. Assertions library

- [x] 3.1 List, from `openspec/specs/user-signup/spec.md`, `openspec/specs/user-signin/spec.md`,
  and `openspec/specs/user-password-reset/spec.md`, every requirement that is independently
  checkable via an HTTP request/response pair (validation rejections, response shape, status
  codes, identical-response requirements where two requests can be compared)
- [x] 3.2 Add `postman/assertions/user-signup.json`, `postman/assertions/user-signin.json`, and
  `postman/assertions/user-password-reset.json`, each entry keyed by the operation's
  `operationId` and citing the requirement name it verifies, with a Postman test-script snippet
  per entry, and verify every requirement listed in 3.1 has a matching entry
- [x] 3.3 Add any additional request variants an assertion needs but the generated collection
  doesn't produce on its own (e.g. a request with a field deliberately omitted, or a pair of
  requests for an identical-response requirement) as `postman/assertions/requests/*.json`
  fragments the merge script inserts alongside the matching generated request, and verify each
  fragment is referenced by at least one assertions entry

## 4. Merge script

- [x] 4.1 Add `postman/merge_assertions.js`: reads `collection.generated.json` and every file
  under `postman/assertions/`, attaches each entry's test script(s) to the request matching its
  `operationId`, inserts any request fragments from 3.3, and gives every remaining request (no
  assertions entry) a default `pm.test('status code is successful', ...)` check; writes
  `postman/collection.merged.json`; verify by running it against the collection generated in 2.2
  and confirming every request in the output has at least one `event: test` entry

## 5. Execution against a live instance

- [x] 5.1 Add a `make ci-serve` (or equivalent script) that runs `migrate` and starts `runserver`
  in the background, polling `GET /api/health/` until it responds, and verify it starts a server
  reachable within the CI job's timeout
- [x] 5.2 Add a `make ci-newman` (or equivalent script) that runs `newman run
  postman/collection.merged.json --reporters cli,json --reporter-json-export
  postman/result.json` against that server, and verify it produces `postman/result.json` and
  exits non-zero when any assertion fails

## 6. Claude evaluation script

- [x] 6.1 Add `postman/review_with_claude.py`: sends `postman/collection.merged.json`,
  `postman/result.json`, and the contents of `openspec/specs/**/spec.md` to a Claude model via
  the Anthropic Messages API (reading the API key from an environment variable, never
  hard-coded), with a prompt applying the blocking/non-blocking contract from
  `openspec/config.yaml`, and requesting the structured JSON verdict shape from design.md
  (`{"findings": [...], "ready": true|false}`)
- [x] 6.2 Make the script parse that JSON, print every finding (blocking and non-blocking) with
  its cited requirement, and exit non-zero if `ready` is `false` or any finding has `blocking:
  true`; verify by running it against a hand-built fixture result/collection pair with one
  deliberately blocking finding and confirming a non-zero exit

## 7. GitHub Actions workflow

- [x] 7.1 Add `.github/workflows/api-behavior-verification.yml`, triggered on `push` to `main`,
  running in order: checkout, set up Python and install `sdd_django_demo/requirements.txt`,
  generate the schema (1.1), set up Node and install `postman/` dependencies (2.1), generate the
  collection (2.2), merge assertions (4.1), start the server (5.1), run Newman (5.2), run the
  Claude evaluation (6.1-6.2) with the Anthropic API key from a repository secret; verify the job
  fails if either the Newman step or the Claude evaluation step exits non-zero
- [x] 7.2 Verify the workflow file is valid by running it through `actionlint` or GitHub's
  workflow syntax check (`gh workflow view` after pushing, or a local `act -n` dry run if
  available)

## 8. Documentation

- [x] 8.1 Add `postman/README.md` documenting the responsibility split from proposal.md (OpenAPI
  = what endpoints exist, specs = how they should behave, Postman/Newman = execution, Claude =
  evaluation, GitHub Actions = automatic pass/fail), how to run the pipeline locally, and how to
  add coverage for a new endpoint (write an assertions-library entry; the collection needs no
  edit)
- [x] 8.2 Add a row/section to `sdd_django_demo/README.md`'s process description pointing to
  `postman/README.md` for this verification layer, alongside the existing `/code-review` step

## 9. Tests (after implementation, from the spec)

- [x] 9.1 List every requirement in `specs/api-behavior-verification/spec.md` and what a test
  would need to assert, working only from the spec
- [x] 9.2 Add a unit test for `merge_assertions.js` (Node's built-in test runner is sufficient -
  no new test framework dependency) asserting: a request whose `operationId` has an assertions
  entry gets that entry's script, and a request with no entry gets only the default status-code
  check
- [x] 9.3 Add a unit test for `review_with_claude.py`'s verdict parsing (mocking the Anthropic
  API response) asserting: a `ready: false` response and a response with a `blocking: true`
  finding both produce a non-zero exit, and an all-clear response produces a zero exit
- [x] 9.4 Run the full pipeline locally end to end (schema -> collection -> merge -> serve ->
  Newman -> Claude evaluation) against the current endpoints (health, signup, signin,
  password-reset, password-reset/confirm) and confirm it passes
- [x] 9.5 Prove the pipeline can actually fail: deliberately break one endpoint's behaviour (or
  introduce a wrong assertion), confirm the run fails and names the right requirement or
  assertion, then restore it and confirm the run passes again

## 10. Traceability and review

- [x] 10.1 Build `traceability.md` mapping every requirement in
  `specs/api-behavior-verification/spec.md` to the code/config that satisfies it and the test
  that verifies it
- [x] 10.2 Run `/code-review` - findings block only if they cite a requirement, a specific named
  failing test, or a documented convention
- [x] 10.3 Fix any blocking findings and re-run `/code-review` once (verify-only pass) until it
  returns `Ready to merge: yes`
- [x] 10.4 Post `proposal.md` and `specs/api-behavior-verification/spec.md` as a comment on issue
  #38 (`gh issue comment 38 --repo awais786/ai-on-boarding`), so the issue stays self-contained
