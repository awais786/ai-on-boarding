# api-behavior-verification

Automatically checks, on every push to `main`, that the live API's real HTTP behaviour matches
what the [OpenSpec specs](../openspec/specs/) say it should do. See
[`openspec/changes/archive/`](../openspec/changes/archive/) once archived, or
`openspec/changes/add-api-behavior-verification/` for the proposal/spec/design this pipeline was
built from.

## Responsibility split

Five things, five separate jobs - this is the whole point of the design:

| Layer | Answers | Lives in |
|---|---|---|
| **OpenAPI** | What endpoints exist? | `sdd_django_demo/api/` (drf-spectacular reads the views) -> `schema.json` |
| **OpenSpec specs** | How should each endpoint behave? | `../openspec/specs/<capability>/spec.md` |
| **Postman / Newman** | Execute the checks | `collection.generated.json` -> `collection.merged.json`, run by `newman` |
| **Claude** | Does the implementation satisfy the specs? Is the checking itself good enough? | `review_with_claude.py` |
| **GitHub Actions** | Run all of the above automatically and enforce pass/fail | `../.github/workflows/api-behavior-verification.yml` |

Endpoint coverage (`generate_collection.js`) and behavioural correctness (the assertions library,
below) are **independent inputs that only meet at merge time** (`merge_assertions.js`). Nothing
in this directory hand-lists an endpoint: add a view, expose it via a URL, and it appears in
`schema.json` and therefore in the collection on the next run, with no change to this pipeline.

## The assertions library

`assertions/<capability>.json` holds, per OpenAPI `operationId`, one entry per requirement it
checks:

```json
{
  "capability": "user-signup",
  "operationId": "signup_create",
  "entries": [
    {
      "requirement": "Reject a missing email",
      "variant": "missing_email",
      "script": "pm.test('...', function () { ... });"
    }
  ]
}
```

- `requirement` must match a `### Requirement:` name in that capability's spec verbatim - this is
  what lets the Claude evaluation step (and a human) trace a check back to the spec.
- `variant` is optional. Omit it (or use `"base"`) to attach the script to the single example
  request the converter generated for that operation. Most requirements need a *different* body
  than the auto-generated example (a field missing, a malformed value, a second request that
  reuses a value from the first) - that's what `variant` points at.
- A named `variant` must have a matching request fragment in `assertions/requests/<file>.json`
  (see below). `merge_assertions.js` clones the base request, applies the fragment's `body` and
  optional `pre_request_script`, and inserts it into the collection right after the base request.

A request fragment:

```json
{
  "operationId": "signup_create",
  "variant": "missing_email",
  "name": "signup - missing email",
  "body": { "username": "...", "password": "...", "country": "US" },
  "pre_request_script": "pm.collectionVariables.set('x', ...);"
}
```

Multi-request scenarios (duplicate detection, the identical-response guarantee, the rate limit)
chain fragments through Postman collection variables set in one fragment's `pre_request_script`
and read by a later one's `body` or test script - `merge_assertions.js` preserves the order
fragments are listed in, so a "setup" fragment must come before the one that depends on it.

**Every** request in the final collection gets at least one test: an operation with no assertions
entry at all still gets a default check (`no server error - <500`, not "succeeded", since the
converter's auto-generated example body for a POST is often placeholder data no real endpoint
should accept). That default is the honest floor, not a substitute for a real assertion - which
is exactly what the Claude evaluation step below is checking for.

## Adding coverage for a new endpoint

1. Expose it through a normal DRF view (it'll appear in `schema.json` / the generated collection
   automatically - no step needed here).
2. Read its capability's spec under `../openspec/specs/`.
3. Add an `assertions/<capability>.json` (or add entries to an existing one) - one entry per
   requirement you can check via an HTTP request/response. If a requirement needs a request body
   the auto-generated example doesn't provide, add a fragment to
   `assertions/requests/<capability>.json`.
4. If a requirement genuinely can't be checked this way (needs a 30-minute wait, true
   concurrency, inspecting outbound email, or database state), add it to
   `assertions/out_of_scope.json` with a one-line rationale instead of skipping it silently - the
   Claude evaluation step treats an undocumented gap and a documented one very differently.
5. Run the pipeline locally (below) and confirm the new checks attach and pass/fail as expected.

Nothing here requires touching `generate_collection.js`, `merge_assertions.js`, or the workflow.

## Known exclusions

See `assertions/out_of_scope.json` for the full, current list of requirements this pipeline
deliberately does not check, each with its own rationale (time-based expiry, true concurrency,
outbound-email inspection, database-only state, no HTTP endpoint of its own, or - for the
reset-password HTML page - a view that is deliberately excluded from the OpenAPI schema and so
is structurally outside this pipeline's reach; it's covered instead by
`sdd_django_demo/api/test_password_reset.py`).

Building this pipeline originally surfaced real drift between `../openspec/specs/` and the live
API - signup requiring an undocumented `username`, and signin's identifier field being
`email_or_username` rather than the `email` the specs described. That drift is now closed:
`openspec/changes/archive/2026-09-01-add-user-signin/` restored and archived the design that
documents both (recovered from a change that was implemented and reviewed, then accidentally lost
in a merge - see that archive's `proposal.md`), and `assertions/user-signup.json` /
`user-signin.json` were rewritten to match and to exercise the newly-documented behaviour
directly (username validation, signin by either identifier, lockout, the indistinguishable-
rejection guarantee). A full local run now passes with zero failures - see `traceability.md` in
`openspec/changes/add-api-behavior-verification/` for what changed and when.

## Running it locally

Before opening a PR, run this from the repo root:

```bash
# 1. Generate the OpenAPI schema
cd sdd_django_demo
make schema                      # -> ../postman/schema.json

# 2. Install Postman tooling (first time only)
cd ../postman
npm install

# 3. Unit-test the merge/review scripts themselves (no server, no API key needed)
npm test                         # 4 Node tests (lib/merge.js) + 12 Python tests (review_with_claude.py)

# 4. Derive the collection from OpenAPI, then attach assertions from the specs
npm run generate                 # -> collection.generated.json
npm run merge                    # -> collection.merged.json

# 5. Start the API and wait for it to be healthy
cd ../sdd_django_demo
make ci-serve

# 6. Run the collection against the live server
cd ../postman
npm run newman                   # -> result.json; prints pass/fail per assertion

# 7. Stop the server
cd ../sdd_django_demo
make ci-stop
```

Expect step 6 to pass with zero failures. Anything failing is worth investigating before opening
a PR.

Then, from `postman/`, the Claude evaluation step:

```bash
pip install -r requirements.txt            # first time only
export ANTHROPIC_API_KEY=...               # or pass --dry-run to skip the call
python3 review_with_claude.py
```

`review_with_claude.py --dry-run` builds the full prompt and prints its size without calling the
API - useful for checking what would be sent without spending a request.

## CI

`.github/workflows/api-behavior-verification.yml` runs the same sequence on every push to `main`
and fails the job if Newman reports a failed assertion or the Claude evaluation's verdict is not
`ready: true` with zero blocking findings. It needs an `ANTHROPIC_API_KEY` repository secret to
run the evaluation step - provisioning that is outside the scope of this pipeline itself. Run
artifacts (`schema.json`, `collection.merged.json`, `result.json`) are uploaded so a failing run
can be inspected without reproducing it locally.
