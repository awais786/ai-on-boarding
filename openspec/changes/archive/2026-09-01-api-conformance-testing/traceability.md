# Traceability: api-conformance-testing

One row per requirement in
[`specs/api-conformance-testing/spec.md`](./specs/api-conformance-testing/spec.md). This capability
is the pipeline itself, not `sdd_django_demo/` application code - "code" below means the
scripts/workflow that implement the requirement, and "test" means what verifies that
implementation. Paths are relative to the repo root unless noted.

| Requirement | Code | Test |
|---|---|---|
| Derive endpoint coverage from the OpenAPI schema | `sdd_django_demo/Makefile:schema` target; `postman/generate_collection.js` + `postman/lib/operationIds.js` | `postman/test/operationIds.test.js` (`schemaOperationIds`, `toSchemaPath`, `stampOperationIds`); manually verified end-to-end against the live schema (tasks.md 1.1/1.3 - all 5 current `operationId`s matched) |
| Source expected behaviour from the capability specs | `postman/assertions/*.json` (each entry's `requirement` field, checked against `openspec/specs/*/spec.md`) | Verified programmatically (tasks.md 5.3): all 47 requirements across `user-signup`, `user-signin`, `user-password-reset` are either cited by a live assertion or listed in `out_of_scope.json`, with no stray citations |
| Keep endpoint coverage and behavioural assertions as independent inputs | `postman/merge_assertions.js` + `postman/lib/merge.js` (joins the two only at merge time, by `operationId`) | `postman/test/merge.test.js` |
| Document requirements that cannot be checked over HTTP | `postman/assertions/out_of_scope.json` | Verified programmatically (tasks.md 5.3), same check as above |
| Execute checks against a live instance of the API | `sdd_django_demo/Makefile:ci-serve`/`ci-stop`; `postman/package.json`'s `newman` script | Manually run locally against a live `runserver` instance (tasks.md 5.3) |
| Fail the run when a live endpoint violates a requirement | `postman/check_results.js`, run after Newman (which itself runs with `--suppress-exit-code` - see "Known drift" in `postman/README.md`) - reads Newman's `result.run.failures` and fails only on a failure not tagged `KNOWN DRIFT` | Manually verified three times across both review rounds (tasks.md 5.5, plus the two round-2 fixes below): corrupting an assertion, and separately forcing a script-level error outside any `pm.test`, both made `npm run check` exit 1 and named the failure correctly; restoring either returned the run to exit 0 with only the two documented `KNOWN DRIFT` failures reported |
| Run automatically after every merge to main | `.github/workflows/api-conformance-testing.yml` (`on: push: branches: [main]`) | Workflow YAML validated with a Python YAML parse (`actionlint` unavailable locally, tasks.md 4.2); not yet observed running in GitHub Actions itself (first real run happens once this change reaches `main`) |
| Keep the merge-time pass/fail gate deterministic | The workflow contains no model/API call; `postman/assertions/*.json` is the only source of pass/fail logic, reviewed like any other committed code | Inspection of `.github/workflows/api-conformance-testing.yml` (no `ANTHROPIC_API_KEY` or equivalent secret is referenced) |

## Code review

**Round 1** (`/code-review`) found 5 issues, all fixed:

1. **Blocking, cites design.md**: the workflow had no way to distinguish the two documented
   `KNOWN DRIFT` failures from a real regression, so it could never go green and a genuine
   regression would be indistinguishable from the accepted ones - contradicting design.md's own
   stated goal. Fixed by adding `postman/check_results.js` as the actual gate: Newman now runs
   with `--suppress-exit-code`, and `check_results.js` fails only on a failure not tagged `KNOWN
   DRIFT`. Verified by re-running the deliberate-break exercise (tasks.md 5.5) under the new gate.
2. `sdd_django_demo/server.log` and `server.pid` (written by `ci-serve`) were not gitignored.
   Fixed in `.gitignore`.
3. Two request fragments accidentally sharing the same `(operationId, variant)` key would have
   silently downgraded the second to the default floor test with no error. Fixed in
   `postman/lib/merge.js` (duplicate fragments now reported as orphaned); covered by a new test in
   `postman/test/merge.test.js`.
4. `ci-serve` captured the wrong PID when Django's autoreloader ran the real listening server as
   a separate child process (confirmed empirically: `server.pid` held one PID, the actual `:8000`
   listener held another). Fixed by adding `--noreload` to `ci-serve`'s `runserver` command - CI
   doesn't need file-watching, and this makes the backgrounded PID and the listening PID the same
   process. Verified: re-ran `make ci-serve` and confirmed `server.pid` matches `lsof -i :8000`'s
   listener.
5. The workflow hand-duplicated `sdd_django_demo/Makefile`'s `setup` target instead of calling it,
   risking drift between the two. Fixed: the workflow's dependency-install step now runs
   `make setup`.

**Round 2** (`/code-review`, follow-up on the round-1 fixes) found one high-severity gap in the
round-1 fix itself, plus 3 further robustness issues; one raised concern was reviewed and found
not applicable. All 4 real issues fixed:

1. **High severity**: `check_results.js` (added in round 1) only inspected each execution's
   `assertions` array, but a script error thrown *outside* a `pm.test(...)` wrapper aborts that
   item's whole script and fires Newman's `'script'` event instead of an `'assertion'` event - it
   lands in `result.run.failures` with **no corresponding `executions[].assertions` entry at
   all**. Reproduced directly: a deliberate script-level `throw` was confirmed to leave
   `execution.assertions` `undefined` for that item, meaning the round-1 `check_results.js` would
   have silently reported the run clean. Fixed by rewriting `check_results.js` to read
   `result.run.failures` (Newman's flat, canonical failure list) instead of walking
   `executions[].assertions`; re-verified with the same reproduction (the script error is now
   caught as an unexpected failure, `error.test === undefined` never matches `KNOWN DRIFT`).
2. A flat string key (`` `${operationId}::${variant || 'base'}` ``) couldn't distinguish "no
   variant" from a variant literally named `"base"` - a fragment/entry using that name would
   silently misattach. Fixed in `postman/lib/merge.js` by grouping entries per operationId into
   `{ base, variants }` instead of a flat keyed string; covered by a new test in
   `postman/test/merge.test.js`.
3. Two base items sharing the same `operationId` (e.g. an OpenAPI schema/converter drift) would
   silently collapse to whichever came last, dropping one request from the run with no report.
   Fixed: duplicate base `operationId`s are now reported as orphaned; covered by a new test.
4. A typo'd or duplicated id in `merge_assertions.js`'s `OPERATION_ORDER` constant was silently
   dropped/duplicated with no diagnostic. Fixed: duplicates are now used only at their first
   occurrence (covered by a new test), and an id listed but never produced by the run now prints a
   warning.

One further concern raised in round 2 - that the "Check results" workflow step could be skipped
because the preceding Newman step lacks `if: always()` - was reviewed and found not applicable:
the round-1 fix already runs Newman with `--suppress-exit-code` (`package.json`'s `newman`
script), so that step never fails on an assertion result in the first place. The reviewing agent
had explicitly not read `package.json`, so it couldn't see this.

All fixes re-verified together after round 2: `npm test` (14/14), the full local pipeline
(tasks.md 5.3, exit 0, exactly the 2 documented `KNOWN DRIFT` failures), and `pytest` (131/131).
**Ready to merge: yes.**

**Round 2** (verify-only): all 5 fixes confirmed in place; `npm test` (11/11), the full local
pipeline (tasks.md 5.3), and `pytest` (131/131) re-run clean after the fixes. **Ready to merge:
yes.**

## Notes

- This traceability table covers the *pipeline's own* 8 requirements. It does not restate the 47
  requirements the pipeline checks against `user-signup`/`user-signin`/`user-password-reset` -
  those already have their own traceability from when those capabilities were built; this change
  adds a second, independent way of verifying them (over live HTTP, post-merge) without altering
  their existing code-level traceability.
- Full local pipeline run (tasks.md 5.3): 53 requests, 70 assertions, 68 passing, exactly 2
  `KNOWN DRIFT` failures (documented in `postman/README.md`, "Known drift"), reproduced twice
  against a fresh database.
- `pytest` for the whole Django project: 131/131 passing, unaffected (tasks.md 5.6) - this change
  touches no `sdd_django_demo/` application code.
- Every row has at least one test or verification step; `postman/test/` has no test that doesn't
  serve a row above. No orphans in either direction.
