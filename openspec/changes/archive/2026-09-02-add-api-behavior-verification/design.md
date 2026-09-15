## Context

See `proposal.md` - Why. The constraints that shape the approach, all confirmed against the
current tree:

- The API already publishes an OpenAPI description. `manage.py spectacular` emits it and covers
  five operations: `GET /api/health/`, `POST /api/signup/`, `POST /api/signin/`,
  `POST /api/password-reset/`, `POST /api/password-reset/confirm/`.
- Two routed addresses carry requirements but are absent from that description: `GET` and `POST`
  on the page served at a delivered reset link. It is served as a plain page rather than through
  the API framework, deliberately and with that reasoning recorded where it is served, so the
  description omits it by design. Eight of the twenty-seven promoted password-reset requirements
  are only observable there.
- Schema generation currently reports an error for `GET /api/health/` - it cannot infer a response
  shape - so that operation is described only as returning 200. No promoted requirement mentions
  that endpoint, so nothing is lost, but generation must not be run in a mode that treats the
  error as fatal.
- A reset code is never returned in a response; that is itself a promoted requirement. The only
  way to hold a usable code is to read the delivered message.
- Delivery is already switchable by environment: setting `RESET_SMTP_HOST` (with `RESET_SMTP_PORT`
  and `RESET_SMTP_TLS`) points delivery at an SMTP server, with a plain-SMTP catcher named in the
  settings' own reasoning as the case that turns TLS off. Nothing in the application changes.
- Promoted requirements today: 12 for signup, 13 for signin, 27 for password reset.
- There is no `.github/` directory. This is the repository's first workflow.

## Goals / Non-Goals

**Goals:**

- One command reproduces locally what the workflow does in CI, so a contributor can see a failure
  without pushing.
- Every gate is enforced by something that fails the run, not by a convention a reviewer has to
  remember.
- Adding an endpoint requires no edit to the verification setup for it to be exercised; it
  requires an edit only to state what that endpoint must do.

**Non-Goals:**

- Changing any application behaviour, dependency, or setting default. The verification run
  supplies environment values the application already reads.
- Replacing `pytest`. Requirements about time, storage, and injected faults stay there.
- Load, performance, or security scanning.

## Decisions

### D1. Derive the collection with an OpenAPI-to-Postman converter, not a bespoke generator

*Requirement: Derive endpoint coverage from the OpenAPI description; Execute the checks as a
Postman collection.*

The build generates the description with `manage.py spectacular`, then converts it with
`openapi-to-postmanv2`. The converter is invoked as a command-line tool; we do not write a
generator.

Alternatives: a hand-written collection - rejected, it is exactly the staleness the change exists
to prevent. A generator of our own reading the description directly - rejected, it reimplements a
maintained converter and we would own every path, method, and body-shape edge case for no gain.

### D2. Prove coverage complete against the routed addresses, and fail when it is not

*Requirement: Account for every address the application routes.*

Deriving from the description answers "which API endpoints exist", but not "which HTTP surfaces
exist" - the reset page is proof of the difference. A build step enumerates every address the
application routes by walking Django's URL resolver, then subtracts three sets:

```
routed addresses
  - present in the OpenAPI description         (derived automatically)
  - declared in surfaces.yaml                  (carries requirements, description omits it)
  - excluded in surfaces.yaml, with a reason   (carries no requirements)
  ────────────────────────────────────────────
  = must be empty, or the run fails
```

This is what keeps the declared list honest. A new endpoint added to the API needs no edit here -
it arrives through the description. A new non-API surface, or a new address of any kind that
nobody has classified, stops the run and names itself. Today's exclusions are the admin site and
the two schema-serving addresses; each records why.

Alternative: trust the description alone - rejected, it silently drops eight promoted
requirements today and would drop any future non-API surface with no signal at all.

### D3. Checks live in a per-capability library, each naming its requirement and scenario

*Requirement: Take expected behaviour from the promoted specs; Check specified behaviour, not only
a successful status.*

One file per capability under `checks/`, mirroring `openspec/specs/`. Each entry names the
requirement and the scenario it verifies, verbatim, so the evaluation can match entries to
promoted text rather than guess. An operation with no entry still receives a status-code check, so
nothing in the collection is unchecked - but the absence of an entry is a coverage gap, not a
pass.

Keying on the capability rather than on the operation is deliberate: requirements are written per
capability, several of them span more than one operation, and matching the specs' own organisation
is what lets the evaluation compare like with like.

### D4. A check is an ordered sequence of requests, not a single request

*Requirement: Express a requirement spanning several requests as an ordered sequence.*

Many promoted requirements are not observable in one response. *Reject all failure modes
identically* requires three refusals compared against each other; *Answer every reset request
identically* requires two; *Reject every bad code identically* requires four; *The old password
stops working* requires a signup, a reset, and two signins in order; *Lock an email out after
repeated failures* requires three failures and then a correct password.

So a library entry is a named sequence: an ordered list of requests, with the checks attached to
whichever request in the sequence can observe the requirement, and earlier responses held in
collection variables so later checks can compare against them. A single-request check is just a
sequence of length one.

This also settles what the converter can and cannot give us. Derived requests carry example
bodies, which are useless for endpoints that need a real address and password. The library
therefore supplies request data as well as checks; the converter supplies the endpoint set, the
method, and the address.

### D5. Read the delivered reset code from a mail catcher

*Requirement: Reach a delivered reset code the way a recipient reaches it.*

The run starts a mail catcher and points delivery at it through the environment the application
already reads. The collection then asks the catcher for the message delivered to a given address
and takes the code from the link, exactly as a recipient does. Twelve password-reset requirements
depend on holding a usable code; without this they cannot be checked at all.

Fetching the message from inside the collection, rather than in shell around it, is what keeps a
sequence like *request a reset, follow the link, submit two entries, confirm the old password
stopped working* a single ordered run with one report.

The check that the response to the reset request does not itself carry the code stays in place and
is asserted directly, so obtaining the code this way cannot mask a regression in the requirement
that forbids returning it.

Alternatives: parse the server's console output - rejected, it couples the run to a log format
that is not a contract. A file-based mail directory read by a shell step - rejected, it moves
extraction outside the collection and splits one sequence across several runner invocations. An
endpoint that returns the code for testing - rejected outright, it builds the exposure that
*Never return the reset code in a response* exists to forbid.

### D6. Record unobservable requirements in three named categories

*Requirement: Record requirements that cannot be observed from outside the process.*

Some promoted requirements cannot be judged by watching HTTP during a run. Naming the categories,
rather than keeping a flat list, makes the register reviewable and tells a contributor which one a
new requirement falls into:

- **`time-bound`** - needs the clock advanced past the run. A reset code expiring after 30
  minutes; a lockout expiring after 30 minutes.
- **`storage-internal`** - asserts on what is stored, not on what is returned. A password stored
  unrecoverably; a confirmation entry not retained.
- **`induced-failure`** - needs a fault injected into infrastructure. Earlier codes staying
  usable when delivery fails.
- **`concurrency`** - needs genuinely simultaneous requests, which a collection runner issuing
  one request after another cannot produce. Two signups for the same address racing each other.

Entries are recorded at scenario granularity where a requirement is only partly unobservable.
*Lock an email out after repeated failures* is the case that forces this: its lockout-triggered
scenario is checkable in a run, its lockout-expires scenario is not, and recording the whole
requirement would quietly drop a check we can perform.

Every entry names what `pytest` already covers it, so the register reads as a division of labour
rather than a list of things nobody checks.

### D7. Execute with Newman and keep the JSON report as the run's evidence

*Requirement: Execute the checks as a Postman collection; Fail the run when observed behaviour
contradicts a requirement.*

Newman is Postman's own collection runner and emits a JSON report recording each request and the
outcome of each check attached to it. That report is the input to the gate and to the evaluation,
so both judge the same evidence.

### D8. The evaluation is a Python step calling Claude with a fixed output shape

*Requirement: Evaluate the checks against the specs before a run may pass.*

A script reads the promoted specs, the built collection, the check library, the register of
unobservable requirements, and Newman's report, and asks `claude-opus-5` to report: promoted
requirements with no check and no register entry, checks that state something other than the
requirement they name, and endpoints checked only for a status code where their spec states more.

The reply is constrained to a fixed schema through the SDK's structured-output support, so the
step yields a list of findings each carrying a requirement name or none, rather than prose a gate
would have to parse. Adaptive thinking is on; the evaluation is a judgement over several documents
and is the one place in the run where reasoning quality decides whether a real gap is caught.

### D9. Two gates, one deterministic and one ratcheted

*Requirement: Fail the run when observed behaviour contradicts a requirement; Fail the run on an
evaluation finding that names a requirement; Fail rather than pass when the evaluation cannot be
performed.*

```
completeness check fails             ──▶ run fails      deterministic
any check in the report fails        ──▶ run fails      deterministic
evaluation cannot run                ──▶ run fails      deterministic
finding naming a requirement,
  not in the unobservable register   ──▶ run fails      judged
finding naming no requirement        ──▶ reported only
```

The register is what makes the judged half safe to put on the critical path: a reasoned, reviewed
gap does not fail the run, but a newly uncovered requirement does. That is a ratchet - coverage
can only be given up deliberately, in a file a reviewer sees.

The blocking rule is not invented here. `openspec/config.yaml` already draws it for code review: a
finding blocks when it cites a requirement, and is a nit otherwise. Using the same rule means a
contributor who understands one understands the other.

The evaluation runs even when checks have already failed, so a run reports coverage findings and
behavioural failures together rather than one at a time.

### D10. All our code is Python; Node supplies two command-line tools

*Requirement: none - this follows the project convention to prefer the simplest arrangement.*

Route enumeration must run inside the Django environment, and the evaluation wants the Anthropic
SDK; both are Python, which is the repository's language. The converter and the runner are Node
programs, but they are invoked as commands with files in and files out. We write no JavaScript,
and the tooling directory holds one dependency manifest for each, not a second codebase.

### D11. Every scenario provisions its own account, at a run-unique address

*Requirement: Check specified behaviour, not only a successful status.*

Reset requests are limited to five per hour per address and signin locks an address out after
three failures, so scenarios that exercise those limits would otherwise interfere with scenarios
that merely need an account. Each sequence creates the accounts it needs at addresses carrying a
per-run token, so order between sequences never changes an outcome.

### D12. The documentation lives with the tooling and is linked from the project's READMEs

*Requirement: Document where coverage and expected behaviour come from.*

A `README.md` beside the tooling states the division - the description supplies the endpoints, the
promoted specs supply expected behaviour, the collection executes, the evaluation judges - together
with the conditions under which a run fails and what to do when it fails on a gap. The repository
and project READMEs link to it, so a contributor adding an endpoint meets it where they already
are.

### D13. Trigger on pushes to `main`, and on request

*Requirement: Run automatically on every push to main.*

The workflow triggers on `push` to `main` and on manual dispatch.

A pull-request trigger would report a violation before it lands rather than after, which is
strictly more useful. It is not adopted here: this repository is developed through forks, and a
workflow run from a fork's pull request cannot read repository secrets, so the evaluation would
have no credential on exactly the runs that matter and would fail every such run under D9. Making
that work needs a decision about `pull_request_target` and its own risks, which is a change of its
own rather than a detail of this one.

## Risks / Trade-offs

- **A model decides part of a merge gate, and models are not deterministic.** → Only findings that
  name a promoted requirement block, and only when that requirement is absent from the register.
  Coverage that has been reasoned about cannot start failing spontaneously; the judged surface is
  narrowed to requirements nobody has yet classified.
- **A run costs an API call and the credential must exist.** → One call per push to `main`. If the
  credential is absent the run fails loudly rather than passing with the evaluation skipped, so a
  missing secret can never be mistaken for a clean run.
- **`main` is red between merging this and the secret being provisioned.** → Deliberate, and the
  order is stated in the migration plan below. A gate that reports success while not running is
  the worse failure.
- **The mail catcher is new infrastructure in the run.** → It is a service container for the life
  of the job, reached only over the settings the application already reads, and it holds nothing
  after the run. No application code, dependency, or default changes.
- **The run exercises a live server, so a startup race would look like a behavioural failure.** →
  The job waits for the health endpoint to answer before the collection runs, and the mail catcher
  likewise, so a timeout is reported as a timeout.
- **The converter's output shape may change between versions and silently alter request names.** →
  The converter is pinned, and the completeness check compares against routed addresses rather
  than against generated names, so a rename cannot quietly drop coverage.
- **The register could become a place to hide real gaps.** → Each entry names a category and the
  `pytest` coverage that stands in for it, and entries are added in reviewed pull requests like
  any other file.

## Migration Plan

1. Land the tooling, the check library, the register, and the workflow together.
2. A maintainer adds the evaluation credential to the repository's secrets. Until it exists, runs
   fail at the evaluation step with a message naming what is missing - by design.
3. **The first run is expected to fail, and the failure is a true finding.** Signup refuses a
   submission carrying the email, username and password its promoted spec describes, because it
   also requires a `country`. No promoted spec mentions `country` at all - its requirements live
   in a capability whose spec has not been promoted - so *Accept a signup submission* says the
   submission should be accepted and the running API refuses it.

   Every check that fails does so downstream of that one refusal: a sequence that cannot create
   an account cannot go on to observe anything else. Nothing fails for a reason traceable to this
   tooling.

   This is not a defect in the tooling and is not suppressed by it. Reconciling it - by promoting
   the spec that describes `country`, or by changing the API - is separate work. Until then the
   workflow reports `main` as failing, which is what it exists to do.
4. Any requirement a run reports as uncovered is either given a check or added to the register
   with a reason; neither is left implicit.
5. Rollback is deleting the workflow file. Nothing else in the repository depends on it, and no
   application behaviour changes when it is absent.

## Open Questions

- Whether to add a pull-request trigger later, and on what terms given the fork constraint in D13.
  Deferrable: it changes when the run happens, not what it checks, and none of the requirements,
  the tooling, or the task breakdown depend on the answer.
