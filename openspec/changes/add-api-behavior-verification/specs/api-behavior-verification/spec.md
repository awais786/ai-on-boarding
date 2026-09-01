## Purpose

Automatically verifies, on every push to `main`, that the API's real HTTP behaviour matches what
its OpenSpec requirements say it should do - with endpoint coverage derived from the OpenAPI
schema so it can never fall out of sync with what's actually deployed, and behavioural correctness
judged against the specs rather than by hand-picked spot checks.

## ADDED Requirements

### Requirement: Run automatically on every push to main
The verification workflow SHALL run automatically whenever a change is pushed to `main`.

#### Scenario: Merge triggers a run
- **WHEN** a commit is pushed to `main` (directly or via a merged pull request)
- **THEN** the verification workflow starts without manual action

### Requirement: Derive endpoint coverage from the OpenAPI schema
The set of endpoints exercised by the workflow SHALL be derived from the API's current OpenAPI
schema, not hand-maintained.

#### Scenario: New endpoint gains coverage without a workflow change
- **WHEN** a new endpoint is implemented and appears in the OpenAPI schema, and no change is made
  to the verification workflow's own configuration
- **THEN** the next run exercises that endpoint

#### Scenario: Removed endpoint drops out automatically
- **WHEN** an endpoint is removed and no longer appears in the OpenAPI schema
- **THEN** the next run does not exercise it, and requires no workflow change to stop doing so

### Requirement: Judge behaviour against the OpenSpec specs
Each endpoint's expected behaviour, for the purpose of this verification, SHALL be defined by the
OpenSpec requirements for the capability that endpoint implements, not by assumptions made outside
those specs.

#### Scenario: Assertion traces to a requirement
- **WHEN** an assertion is added for an endpoint's behaviour
- **THEN** it corresponds to a requirement stated in that endpoint's OpenSpec capability spec

### Requirement: Assert specified behaviour, not just success status codes
For an endpoint whose capability spec defines validation, error, or response-shape requirements,
the workflow SHALL check those requirements, not only that a request returns a successful status
code.

#### Scenario: Validation requirement is checked
- **WHEN** an endpoint's spec requires a request to be rejected under some condition (e.g. a
  missing required field)
- **THEN** the workflow sends a request meeting that condition and checks that it is rejected as
  the spec requires, not merely that some response was returned

#### Scenario: Response shape requirement is checked
- **WHEN** an endpoint's spec constrains what a response body may or must contain
- **THEN** the workflow checks the response body against that constraint, not only the status code

### Requirement: Execute checks with Postman tooling
The workflow SHALL execute the derived, assertion-attached requests against a running instance of
the API using Postman's collection-execution tooling, and SHALL produce a machine-readable result
for each request describing whether every attached assertion passed.

#### Scenario: Every request produces a pass/fail result per assertion
- **WHEN** the workflow executes the collection against a running instance
- **THEN** the result report records, for each request, whether each of its attached assertions
  passed or failed

### Requirement: Fail the run on an assertion failure
The workflow SHALL fail when any behavioural assertion, run against the live API, does not hold.

#### Scenario: A spec-required behaviour is violated
- **WHEN** the running API's response to a request does not satisfy a checked requirement
- **THEN** the workflow run fails

### Requirement: Evaluate coverage and correctness against the specs before passing
Before a run can pass, it SHALL include an automated evaluation of the endpoint checks against the
OpenSpec specs, covering at minimum: requirements with no corresponding assertion, assertions that
do not accurately reflect what their requirement says, and endpoints checked only for a successful
status code where their spec defines more specific behaviour.

#### Scenario: Missing coverage is flagged
- **WHEN** a capability spec defines a requirement for an endpoint and no assertion checks it
- **THEN** the evaluation reports this as a finding

#### Scenario: Incorrect assertion is flagged
- **WHEN** an assertion checks for something other than what its cited requirement actually
  states
- **THEN** the evaluation reports this as a finding

#### Scenario: Status-only endpoint is flagged
- **WHEN** an endpoint's spec defines behaviour beyond a successful response, and that endpoint's
  checks assert only a status code
- **THEN** the evaluation reports this as a finding

### Requirement: Fail the run on a blocking evaluation finding
The workflow SHALL fail when the evaluation required above reports a finding that blocks merge,
using the same blocking/non-blocking distinction (cites a requirement, or is a nit) already used
by this project's code review process.

#### Scenario: Blocking finding fails the run
- **WHEN** the evaluation reports a finding tied to a specific OpenSpec requirement
- **THEN** the workflow run fails and the finding's requirement is named in the run's output

#### Scenario: Non-blocking observation does not fail the run
- **WHEN** the evaluation reports an observation that cites no requirement, no failing check, and
  no documented convention
- **THEN** the workflow run may still pass

### Requirement: Report which requirement failed
When the workflow fails, its output SHALL identify which requirement (or which endpoint, if the
failure is a coverage gap rather than a violation) was responsible.

#### Scenario: Failure output names a requirement
- **WHEN** the workflow fails for any reason covered by this spec
- **THEN** the run's output names the specific requirement or endpoint at fault, not just "checks
  failed"
