## Why

`pytest` verifies behaviour against the Django code from inside the process; nothing verifies the
deployed HTTP surface from outside, and nothing catches an endpoint's real-world behaviour
drifting from its spec after a merge to `main`. Issue #38 asks for that outside-in check, with
endpoint coverage derived from the OpenAPI schema so it can never go stale, correctness judged
against the OpenSpec specs, and a merge to `main` blocked when a specified behaviour breaks.

## What Changes

- Add a generated Postman collection whose requests are derived from the API's OpenAPI schema
  (already produced by drf-spectacular), so every request corresponds to a real, currently-exposed
  endpoint and no endpoint is hand-added to or hand-removed from the collection.
- Add a checked-in library of behavioural assertions, one entry per applicable OpenSpec
  requirement, each keyed to the OpenAPI operation it covers and citing the requirement it
  verifies. Assertions check response status, response body shape/content, and validation/error
  behaviour required by the specs - not just "request succeeded."
  An endpoint with no assertions library entry still gets a default status-code check, so nothing
  in the collection is silently unchecked, but the absence of a specific entry is a coverage gap.
- Run the merged collection against a running instance of the API and produce a machine-readable
  result report.
- Add an automated evaluation step that reads the collection, the result report, and the OpenSpec
  specs, and reports on: requirements with no corresponding assertion, assertions that mis-state
  what their cited requirement actually says, endpoints checked only for a successful status code
  where their spec defines more specific behaviour, and any result showing the live API violating
  a requirement. This mirrors the pass/fail, requirement-cited verdict shape this project's
  `/code-review` already uses.
- Add a GitHub Actions workflow, triggered on push to `main`, that runs the full chain (derive
  coverage → attach assertions → execute against a live instance → evaluate) and fails the run
  when an assertion fails or the evaluation reports a finding that cites a requirement.
- Document the approach - what the OpenAPI schema is responsible for, what the specs are
  responsible for, what the generated checks execute, what the evaluation step judges, and how the
  workflow decides pass/fail - so a future contributor knows where behavioural coverage for a new
  endpoint comes from.

## Capabilities

### New Capabilities

- `api-behavior-verification`: an automated, spec-derived check that the running API's observable
  behaviour matches its OpenSpec requirements - endpoint coverage derived from the OpenAPI schema,
  correctness judged against the specs, executed on every push to `main`, and blocking the run on
  a spec violation or a blocking coverage gap.

### Modified Capabilities

(none - this change verifies existing API behaviour; it does not change what the API does)

## Impact

- Affected code: a new top-level tooling directory (collection-generation, the assertions
  library, and the merge/evaluation scripts) and a new `.github/workflows/` file - the first
  GitHub Actions workflow in this repository. No changes to `sdd_django_demo/` application code.
- Affected process: this repo's process documentation gains a description of this verification
  layer, alongside the existing `/code-review` step.
- New dependencies: CI-only tooling to derive a Postman collection from an OpenAPI schema and to
  execute it (e.g. an OpenAPI-to-Postman converter and Newman) - not runtime dependencies of the
  Django project.
- New CI secret required: credentials for the automated evaluation step to call Claude (to be
  added to the repository's GitHub Actions secrets by a maintainer - outside the scope of this
  change to provision).
- Scope note: this change builds the verification pipeline itself. Coverage at merge time is
  whatever the OpenAPI schema currently exposes - today that's `health`, `signup`, `signin`, and
  the password-reset request/confirm endpoints. A future endpoint gains coverage automatically,
  with no pipeline change, once it's exposed through the schema; its assertions library entries
  are written when that endpoint's requirements need more than the default status-code check.
