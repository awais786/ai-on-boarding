# api-conformance-testing

Automatically checks, on every push to `main`, that the live API's real HTTP behaviour matches
what the [OpenSpec specs](../openspec/specs/) say it should do. Built from
`openspec/changes/api-conformance-testing/` (proposal, delta spec, design, tasks) - see that
directory (or its archived copy) for the full reasoning.

## Responsibility split

Four things, four separate jobs - this is the whole point of the design:

| Layer | Answers | Lives in |
|---|---|---|
| **OpenAPI** | What endpoints exist? | `sdd_django_demo/api/` (drf-spectacular reads the views) -> `schema.json` |
| **OpenSpec specs** | How should each endpoint behave? | `../openspec/specs/<capability>/spec.md` |
| **Postman / Newman** | Execute the checks | `collection.generated.json` -> `collection.merged.json`, run by `newman` |
| **GitHub Actions** | Run all of the above automatically and enforce pass/fail | `../.github/workflows/api-conformance-testing.yml` |

There is deliberately no fifth "live model call" layer inside the workflow. A model (Claude) is
useful for *authoring and reviewing* the assertions library below - deciding whether a check is
missing or wrong against a spec - and that happens once, as a normal reviewed change to this
directory, not on every push to `main`. The merge-time gate is Newman running the committed,
already-reviewed assertions: deterministic, no API call, no variance between two runs of the same
code. See `design.md`'s "Keep the merge-time pass/fail gate deterministic" decision for the full
rationale, including why this change takes a different position than an earlier PR on the same
request.

Endpoint coverage (`generate_collection.js`) and behavioural correctness (the assertions library,
below) are **independent inputs that only meet at merge time** (`merge_assertions.js`). Nothing
in this directory hand-lists an endpoint: add a view, expose it via a URL, and it appears in
`schema.json` and therefore in the collection on the next run, with no change to this pipeline.

## The assertions library

`assertions/<capability>.json` holds a flat list of entries, each naming the OpenAPI
`operationId` it attaches to, the exact `### Requirement:` name (from that capability's spec) it
verifies, and one or more Postman `pm.test(...)` scripts:

```json
{
  "capability": "user-signup",
  "entries": [
    {
      "operationId": "signup_create",
      "requirement": "Reject a missing email",
      "variant": "missing_email",
      "test": [
        "pm.test('Reject a missing email', function () {",
        "    pm.response.to.have.status(400);",
        "    pm.expect(pm.response.json()).to.have.property('email');",
        "});"
      ]
    }
  ]
}
```

- `requirement` must match a `### Requirement:` heading in that capability's spec verbatim -
  never a scenario name. That's what lets a human (or a future automated check) trace an
  assertion back to the spec it verifies.
- `variant` is optional. Omit it to attach the script to the single example request the
  converter generated for that operation. Most requirements need a *different* request body than
  the auto-generated placeholder (a field missing, a weak password, a second request reusing an
  email the first one just registered) - that's what `variant` points at.
- A named `variant` must have a matching request fragment in `assertions/requests/<file>.json`
  (see below). `merge_assertions.js` clones the base request, applies the fragment's body, and
  inserts it into the collection right after the base request, in the order fragments are listed.

A request fragment:

```json
{
  "operationId": "signup_create",
  "variant": "missing_email",
  "name": "signup - missing email",
  "body": { "username": "conformance_missing_email", "password": "Passw0rd1", "country": "US" }
}
```

**Fixture data uses whatever the live endpoint actually requires; assertions test only what the
spec claims about behaviour.** Signup's live serializer requires `username` and `country` beyond
what the canonical spec describes (see "Known drift" below) - a request fragment supplies those
extra fields because it has to, to reach a state at all, the same way any integration test's
setup data does. What an *assertion* is allowed to check is strictly what the cited requirement
says.

**Cross-endpoint dependencies decide execution order.** `merge_assertions.js`'s `OPERATION_ORDER`
constant runs `signup_create` first, then `signin_create`, then the password-reset operations:
signup's "success" variant creates a shared fixture account (`conformance-fixture@example.com`)
that signin and password-reset assertions sign in with or request a reset for later in the same
run. Newman executes a fresh, empty SQLite database once per CI run, so this ordering is
reliable - there's no seed data or concurrent run to collide with.

**Every** request in the final collection gets at least one test: an operation with no assertions
entry at all still gets a default check (`pm.expect(pm.response.code).to.be.below(500)`, not
"succeeded", since the converter's auto-generated example body for a POST is often placeholder
data no real endpoint should accept). That default is the honest floor, not a substitute for a
real assertion.

## What isn't checked live: `out_of_scope.json`

`assertions/out_of_scope.json` lists every requirement (or specific scenario of an
otherwise-covered requirement) that cannot be verified by an HTTP request/response check, each
with a one-line reason - most commonly because verifying it means reading the content of an
outbound email, waiting a real 30 minutes, true concurrency, or reading a value straight out of
the database. A requirement with neither a live assertion nor an entry here is an undocumented
gap, not a deliberate exclusion.

The password-reset code is the clearest example: it is stored only as a digest
(`PasswordResetCode.code_digest`) and the plaintext code exists nowhere except the outbound
email - no HTTP response ever returns it, by design (see `design.md`'s decision on this). So the
full request-reset -> confirm-reset happy path isn't chained live the way signup -> signin is;
instead, everything about `password_reset_confirm_create` that *can* be exercised without a real
code (field validation, rejecting unrecognised codes identically, proving a rejected completion
leaves the old password intact) is checked live, and the rest goes in `out_of_scope.json`.

## Known drift

Building this pipeline surfaced real drift between `../openspec/specs/` and the live API that
predates this change and is out of scope to fix here (see `design.md`, "Risks / Trade-offs"):

- **Signup** requires `username` and `country` in addition to `email`/`password`, and a
  successful response includes `username` alongside `email` - the canonical spec describes
  neither.
- **Signin**'s identifier field is `email_or_username`, not `email` as the canonical spec
  describes.

Two assertions - `assertions/user-signup.json`'s "Signal success with the created account's
email" and `assertions/user-signin.json`'s "Reject a missing email" - are written strictly from
the canonical specs, so they **currently and correctly fail**. Each is tagged `KNOWN DRIFT` in
its test name. This is the pipeline doing its job, not a defect in it: fixing the drift (by
updating the code or by writing and archiving specs that describe the current behaviour) is
separate follow-up work.

Because these two failures are permanent until that follow-up work happens, Newman itself runs
with `--suppress-exit-code` (see `package.json`'s `newman` script) - if Newman's raw exit code
gated the workflow, it could never go green, and a genuinely new regression would be
indistinguishable from the two accepted failures. `check_results.js` is the actual gate: it reads
Newman's `result.json` and fails only on an assertion failure whose test name is **not** tagged
`KNOWN DRIFT`. Run it after Newman, locally or in CI, via `npm run check`.

## Adding coverage for a new endpoint

1. Expose it through a normal DRF view (it appears in `schema.json` / the generated collection
   automatically - no step needed here).
2. Read its capability's spec under `../openspec/specs/`.
3. Add entries to `assertions/<capability>.json` - one per requirement you can check via an HTTP
   request/response, citing the requirement's exact name. If a requirement needs a request body
   the auto-generated example doesn't provide, add a fragment to
   `assertions/requests/<capability>.json`.
4. If a requirement genuinely can't be checked this way, add it to `assertions/out_of_scope.json`
   with a one-line rationale instead of leaving it silently uncovered.
5. Run the pipeline locally (below) and confirm the new checks attach and pass/fail as expected.

Nothing here requires touching `generate_collection.js`, `merge_assertions.js`, or the workflow.

## Running it locally

```bash
# 1. Generate the OpenAPI schema
cd sdd_django_demo
make schema                      # -> ../postman/schema.json

# 2. Install Postman tooling (first time only)
cd ../postman
npm install

# 3. Unit-test the merge script itself (no server needed)
npm test

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

# 8. Check the results (the actual pass/fail gate - see "Known drift" above)
cd ../postman
npm run check
```

Expect step 6 to report exactly the two `KNOWN DRIFT` failures listed above - not zero, and not
more - and step 8 to exit 0, printing those same two as documented and nothing under "unexpected
assertion failure(s)". Anything else is worth investigating before opening a PR.

## CI

`.github/workflows/api-conformance-testing.yml` runs the same sequence on every push to `main`
and fails the job if `check_results.js` reports an assertion failure not tagged `KNOWN DRIFT`. No
repository secret is required - there is no model call in this workflow. Run artifacts
(`schema.json`, `collection.merged.json`, `result.json`) are uploaded so a failing run can be
inspected without reproducing it locally.
