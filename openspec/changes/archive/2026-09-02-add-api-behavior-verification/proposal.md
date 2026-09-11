## Why

`pytest` proves the application code satisfies its specs from inside the process. Nothing checks
that the running API, reached over HTTP the way a real caller reaches it, still behaves the way
`openspec/specs/` says it should - and nothing notices when a merge to `main` breaks a specified
behaviour. Any hand-written check of that kind would also rot: endpoints get added and removed,
and a hand-maintained list of them silently falls behind.

## What Changes

- Add an automated verification pass that exercises the running API over HTTP and judges what it
  observes against the requirements in `openspec/specs/`.
- Derive the set of exercised endpoints from the API's published OpenAPI description rather than
  hand-listing them, so a new endpoint is covered without touching the verification setup and a
  removed one drops out on its own.
- Cover the HTTP surfaces that carry requirements but are absent from the OpenAPI description -
  today, the page served at a delivered password-reset link. These are declared explicitly, and a
  completeness check fails the run when any routed address is neither derived, declared, nor
  excluded with a written reason. Nothing can be missed silently.
- Add a reviewable library of behavioural checks, each citing the requirement it verifies by name.
  A check may span an ordered sequence of requests, because many requirements are only observable
  across several - that two rejections are indistinguishable, that an old password stops working
  after a reset, that an address is locked out after repeated failures.
- Check what the specs actually require - rejection status and body, response shape and content,
  what a response must never contain - not merely that a request succeeded.
- Record which requirements are not observable from outside the process at all, each with its
  reason: those needing the clock advanced past the run, those asserting on what is stored rather
  than what is returned, and those needing a fault injected into infrastructure. `pytest` already
  covers these; this pass does not duplicate it.
- Add an automated evaluation of the checks against the specs, reporting requirements with no
  check, checks that misstate the requirement they cite, and endpoints checked only for a status
  code where their spec requires more.
- Add a GitHub Actions workflow - the first in this repository - that runs the whole pass on every
  push to `main`, and on manual dispatch. The run fails when an observed behaviour contradicts a
  requirement, when the completeness check finds an unaccounted-for address, or when the
  evaluation reports a finding citing a requirement that is not already recorded as unobservable.
- Document where endpoint coverage comes from, where expected behaviour comes from, and how the
  run decides pass or fail, so a contributor adding an endpoint knows what is expected of them.

## Capabilities

### New Capabilities

- `api-behavior-verification`: automated verification that the running API's observable HTTP
  behaviour matches the requirements in `openspec/specs/` - coverage derived from the OpenAPI
  description and proven complete against the routed addresses, correctness judged against the
  specs, run on every push to `main`, and failing the run on a contradicted requirement.

### Modified Capabilities

(none - this change verifies existing behaviour; it does not change what the API does)

## Impact

- New top-level `tooling/api-verification/` directory holding the check library, the collection
  build, the completeness check, and the evaluation step. New `.github/workflows/` file.
- No change to `sdd_django_demo/` application code, its dependencies, or its behaviour. The
  verification run configures the existing `RESET_SMTP_*` settings to point delivery at a mail
  catcher so that a delivered reset code can be followed the way a recipient follows it; that
  path already exists and is unchanged.
- New CI-only tooling, not runtime dependencies of the Django project: an OpenAPI-to-collection
  converter, a collection runner, and a mail catcher service for the run.
- New repository secret required for the evaluation step. A maintainer must add it; until it
  exists the workflow fails rather than passing with the evaluation skipped.
- Verification is bounded by what `openspec/specs/` currently states. A capability whose spec has
  not yet been promoted is not verified, and gains coverage automatically once it is.
