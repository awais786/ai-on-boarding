## Context

See proposal.md - Why. Relevant current state:

- `drf-spectacular` is already installed and wired up: `GET /api/schema/` serves the OpenAPI 3
  schema for every DRF view, and `manage.py spectacular` (its own management command) can write
  that same document to a file without a server running.
- There is no `.github/workflows/` directory anywhere in this repo yet - this is the first
  GitHub Actions workflow.
- `openspec/specs/` holds three canonical capability specs today (`user-signup`, `user-signin`,
  `user-password-reset`).
- Password-reset codes are stored only as a digest (`PasswordResetCode.code_digest`); the
  plaintext code exists nowhere except the outbound email. No HTTP response ever returns it -
  deliberately, since returning it would itself be a credential-exposure bug.
- This project already has a requirement -> code -> test traceability convention
  (`traceability.md` per change) and a blocking/non-blocking review contract used by
  `/code-review` (`openspec/config.yaml` - `operations.apply.guidance`). Both are reused here.

## Goals / Non-Goals

**Goals:**
- Satisfy every requirement in `specs/api-conformance-testing/spec.md` with a pipeline that keeps
  OpenAPI (coverage), the specs (behaviour), and Postman/Newman (execution) as independent inputs
  combined only at run time, per *Keep endpoint coverage and behavioural assertions as
  independent inputs*.
- Keep the automated merge-time gate deterministic (Newman only), per *Keep the merge-time
  pass/fail gate deterministic*, so a red run always traces to a specific, previously reviewed
  assertion rather than to live model output.

**Non-Goals:**
- Not a replacement for `pytest` - `pytest` verifies behaviour against the Django code
  in-process; this pipeline verifies the deployed HTTP surface from outside, after merge.
- Not full response-schema validation against the OpenAPI schema (exhaustive type/format
  checking of every field) - assertions are scoped to what the capability specs actually state.
- Not a mechanism for closing the password-reset-code gap by exposing the code over HTTP in any
  environment - see Decisions below for how that gap is handled instead.
- Not a fix for any drift this pipeline finds between current specs and current API behaviour -
  per proposal.md, that is separate follow-up work.

## Decisions

**Generate the schema with `manage.py spectacular --file schema.json`, not by scraping a live
server.** This produces the same document `/api/schema/` serves, but as a build artifact the CI
job can create before the server needs to be running - decoupling "what endpoints exist" from
"is the server currently up." Alternative considered: fetch `/api/schema/` from an
already-started dev server - rejected, since it makes coverage generation depend on server
startup timing for no benefit.

**Convert schema to a collection with Postman's own `openapi-to-postmanv2` converter, execute
with Newman.** Both are maintained by Postman, are the standard tool for exactly this shape of
pipeline, and avoid hand-writing a converter. CI-only Node dependencies, isolated from the
Django project's own `requirements.txt`.

**Assertions live in a committed library, keyed by OpenAPI `operationId`, separate from the
generated collection; a merge step combines them at run time.** Each entry names the requirement
it verifies and one or more Postman test-script snippets. A request whose `operationId` has no
library entry still gets a minimal default check (no server error, i.e. status < 500) so nothing
executes with zero assertions - but that default is the honest floor, not a substitute for a
real assertion; a genuinely uncheckable requirement belongs in the out-of-scope list instead,
not silently behind the default. This is what satisfies *Keep endpoint coverage and behavioural
assertions as independent inputs*: an endpoint appearing or disappearing changes only the
generated collection; a requirement changing changes only the assertions library; neither edits
the other.

**The out-of-scope list closes the password-reset-code gap, rather than scraping the console
email backend for the code.** Confirming a reset requires a code that only ever reaches the
user's email - never an HTTP response - by design. Teaching the conformance pipeline to read the
server's outbound mail (e.g. parsing console-backend log output) would work, but adds test-only
plumbing whose own correctness would need verifying, for a flow `pytest` already exercises
in-process (it can read `PasswordResetCode` directly). Requirements that depend on knowing the
code are recorded in the out-of-scope list with that rationale; requirements that don't -
identical-response behaviour for a known vs. unknown email, rejecting a malformed or already-used
code - are still checked live.

**The merge-time workflow makes no model API call; a model may assist authoring the assertions
library as a separate, human-reviewed step.** Directly implements *Keep the merge-time pass/fail
gate deterministic*. Alternative considered: have a model evaluate the run's results against the
specs on every push, as an additional or sole gate - rejected because it makes CI's pass/fail
depend on live model output on every merge (cost, latency, and a run that can go red for reasons
that aren't a fixed, citable assertion), for a check that reviewed, spec-derived Newman
assertions already provide deterministically. Authoring/reviewing the assertion library is where
a model's judgment about spec coverage is actually useful, and that happens once per
endpoint/spec change, not once per merge.

**Requirement names in failure output come straight from the assertions library**, not from
parsing Newman's free-text output - each merged assertion's Postman test name is set to the
requirement name (or "default: no server error" for the fallback) at merge time, so a failing
run's output is just that name, satisfying *Fail the run when a live endpoint violates a
requirement* without extra parsing logic.

## Risks / Trade-offs

- [A live server in CI is heavier than pytest's in-process test client] -> deliberate: this
  pipeline exists specifically to check the deployed HTTP surface, which an in-process client
  can't do. SQLite and no required environment variables keep the server trivial to start.
- [The assertions library can drift out of sync with the specs the same way any hand-written
  test could] -> mitigated by requiring assertion authorship/updates to be reviewed against the
  spec they cite (optionally model-assisted) before being committed, same as any other reviewed
  code change in this project.
- [Building this may surface pre-existing drift between current specs and current live
  behaviour] -> expected, not a defect in the pipeline; per proposal.md, fixing that drift is
  explicitly out of scope for this change. If it occurs, the resulting failing assertions should
  be clearly identifiable as drift findings (naming the requirement) so a maintainer can decide
  whether to fix the code or the spec, rather than being indistinguishable from a regression.
- [`operationId` is the join key between the assertions library and the generated collection, so
  a drf-spectacular default `operationId` change would silently orphan an assertions entry] ->
  an orphaned entry (a requirement with no matching request in the merged collection) should be
  detectable as part of adding/reviewing assertions, so it surfaces as a gap rather than passing
  silently.
