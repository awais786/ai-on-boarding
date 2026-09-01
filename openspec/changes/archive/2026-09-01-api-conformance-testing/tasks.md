## 1. OpenAPI schema and generated collection

- [x] 1.1 Add a `schema` target (Makefile or equivalent) that runs `manage.py spectacular --file
  postman/schema.json`, and verify the generated file lists `operationId`s for `health`,
  `signup`, `signin`, `password-reset`, and `password-reset-confirm`
- [x] 1.2 Create the `postman/` directory with its own `package.json`; add `openapi-to-postmanv2`
  and `newman` as dev dependencies, and verify `npm install` succeeds
- [x] 1.3 Add `postman/generate_collection.js` converting `schema.json` into
  `collection.generated.json`, and verify the output collection contains one request per
  `operationId` from the schema

## 2. Assertions library

- [x] 2.1 Read `openspec/specs/user-signup/spec.md`, `user-signin/spec.md`, and
  `user-password-reset/spec.md`; for each requirement that can be verified over HTTP, add an
  entry to `postman/assertions/<capability>.json` keyed by the relevant `operationId`, naming the
  requirement it verifies and a Postman `pm.test(...)` script
- [x] 2.2 Add request fragments to `postman/assertions/requests/<capability>.json` for any
  requirement whose check needs a request body or chained value the auto-generated example
  request doesn't provide (e.g. a missing field, a duplicate submission, a second request reusing
  a value from the first)
- [x] 2.3 Add `postman/assertions/out_of_scope.json` listing every requirement that cannot be
  checked over HTTP (per design.md - password-reset-confirm's happy path needs a code that only
  ever reaches an email, time-based expiry, true concurrency), each with a one-line rationale

## 3. Merge step

- [x] 3.1 Implement `postman/merge_assertions.js`: for each request in the generated collection,
  attach its assertions-library entry's test script(s) if one exists by `operationId`, insert any
  variant request fragments in the order listed, and attach a default `status < 500` test to any
  request left with no library entry; write the result to `collection.merged.json`
- [x] 3.2 Verify every request in `collection.merged.json` carries at least one test script, and
  that every assertions-library entry has a matching request in the output (no orphaned entry)

## 4. CI workflow

- [x] 4.1 Add `.github/workflows/api-conformance-testing.yml`, triggered on `push` to `main`:
  install Python/Node dependencies, generate the schema, install `postman/` tooling, run the
  generate and merge steps, run `manage.py migrate` and start the API in the background, poll
  `GET /api/health/` until it responds, run `newman run collection.merged.json` against it, stop
  the server, and upload `schema.json` / `collection.merged.json` / Newman's result file as run
  artifacts
- [x] 4.2 Verify the workflow file is syntactically valid (`actionlint` if available, otherwise
  a YAML parse check) - actionlint not available locally; validated with a Python YAML parse
  instead

## 5. Tests (after implementation, from the spec)

- [x] 5.1 List every requirement in `specs/api-conformance-testing/spec.md` and what a test would
  need to assert, working only from the spec
- [x] 5.2 Write `postman/test/merge.test.js` covering `merge_assertions.js`: the default fallback
  check is applied when no library entry exists, a library entry's script attaches to the correct
  request by `operationId`, a variant fragment is inserted with its own body, and an orphaned
  assertions-library entry is detectable in the merge output
- [x] 5.3 Run the full local pipeline (schema -> generate -> merge -> serve -> newman) and
  confirm every HTTP-checkable requirement across the three capability specs is either covered by
  a passing assertion or listed in `out_of_scope.json` - no undocumented gaps. Verified
  programmatically: all 47 requirements across the three specs are either live-covered or
  documented out of scope, no gaps, no stray citations.
- [x] 5.4 If any assertion legitimately fails against current live behaviour (pre-existing drift
  between a spec and the deployed code, not a bug in the pipeline itself), document it - the
  requirement name, the expected vs. observed behaviour - rather than weakening the assertion to
  force a pass; flag it for a maintainer decision, per design.md's noted risk. Two assertions
  legitimately and reproducibly fail, both tagged `KNOWN DRIFT` in their test name and documented
  in postman/README.md: signup's success response includes `username` alongside `email` (the
  canonical spec describes only `email`), and signin's identifier field is `email_or_username`,
  not `email` as the canonical spec describes. Same drift PR #39 found independently.
- [x] 5.5 Deliberately break one assertion's underlying behaviour (or the assertion itself),
  confirm the pipeline fails and names the right requirement, then restore it. Confirmed: with
  `Reject a missing password`'s assertion corrupted, Newman failed exactly that assertion, naming
  it precisely; restoring it returned the run to the same 2 documented KNOWN DRIFT failures.
- [x] 5.6 Run `pytest` for the whole Django project and confirm it is unaffected (this change
  touches no `sdd_django_demo/` application code). 131/131 passing.

## 6. Documentation

- [x] 6.1 Write `postman/README.md` documenting the responsibility split (OpenAPI = coverage,
  specs = behaviour, Postman/Newman = execution, GitHub Actions = automatic trigger), how to add
  assertion coverage for a new endpoint, and how to run the pipeline locally

## 7. Traceability and review

- [x] 7.1 Build `traceability.md` mapping every requirement in
  `specs/api-conformance-testing/spec.md` to the script or workflow step that implements it and
  the test that verifies it
- [x] 7.2 Run `/code-review` - address any blocking findings. Round 1 found 5 issues (a
  gate that could never go green, ungitignored server.log/pid, a silent duplicate-fragment
  downgrade, a PID/autoreloader mismatch, workflow/Makefile setup duplication) - all fixed. See
  `traceability.md`, "Code review".
- [x] 7.3 Run `/code-review` again (verify-only) - confirm `Ready to merge: yes`. Round 2 found
  one high-severity gap in the round-1 fix itself (script-level errors outside `pm.test` were
  invisible to `check_results.js`) plus 3 further robustness issues - all fixed and re-verified.
  `Ready to merge: yes` - see `traceability.md`, "Code review".
