## Why

Nothing today checks that the live, deployed API actually behaves the way `openspec/specs/`
says it should. `pytest` proves the Django code satisfies its specs in-process, but a caller
hitting the real HTTP endpoints after a merge to `main` has no automated check standing behind
them, and endpoint coverage for any such check would otherwise have to be hand-maintained
against `sdd_django_demo/api/urls.py` as endpoints are added. Requested via issue #38.

## What Changes

- New GitHub Actions workflow, triggered on push to `main`, that verifies the live API against
  the specs and fails the run when an endpoint violates a documented requirement.
- Endpoint coverage is derived from the OpenAPI schema (`drf-spectacular`, already installed) —
  never hand-listed — so a new endpoint is picked up automatically once it exists.
- Behavioural assertions come from `openspec/specs/`, kept in a committed, reviewable library
  keyed by each endpoint's OpenAPI `operationId`, with every assertion citing the `### Requirement:`
  name it verifies.
- A documented, explicit list of requirements that cannot be checked over plain HTTP (needs to
  read outbound email, true concurrency, a time-based wait) rather than a silent gap.
- Claude's role is authoring and reviewing that assertions library against the specs — done when
  an endpoint or spec changes, as a normal reviewed artifact — not a live model call inside the
  merge-time workflow. The merge-time gate is Newman running the assertions deterministically;
  nothing about whether `main` goes red depends on a model call.
- **Not in scope**: fixing any drift this surfaces between the current specs and the live API's
  actual behaviour. This pipeline only reports drift against the requirements as currently
  written; correcting the code or the specs to resolve a mismatch is separate follow-up work.

## Capabilities

### New Capabilities
- `api-conformance-testing`: derives endpoint coverage from the OpenAPI schema, sources expected
  behaviour from the existing capability specs, executes checks with Postman/Newman against a
  live server, and fails a post-merge GitHub Actions run on any violation.

### Modified Capabilities
(none — this change adds a verification pipeline; it does not alter what `user-signup`,
`user-signin`, or `user-password-reset` require)

## Impact

- Adds `.github/workflows/` (does not exist in this repo today) with one workflow file.
- Adds a new `postman/` directory: a generated-from-schema collection, a committed assertions
  library, a merge step that combines them, and an out-of-scope list — no application code in
  `sdd_django_demo/` is touched.
- New CI-only dependencies (Node/Postman tooling for schema→collection conversion and Newman;
  no new Python runtime dependency for the Django project itself).
- No changes to `sdd_django_demo/api/` behaviour, migrations, or existing `pytest` suite.
