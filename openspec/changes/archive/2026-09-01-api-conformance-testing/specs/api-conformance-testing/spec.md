## Purpose

Automatically verifies, after every merge to `main`, that the live API's actual HTTP behaviour
matches what `openspec/specs/` says it should do — closing the gap between specs proving out
in-process (via `pytest`) and the deployed surface a real caller hits.

## ADDED Requirements

### Requirement: Derive endpoint coverage from the OpenAPI schema
The system SHALL determine which endpoints to check from the project's OpenAPI schema, not from
a hand-maintained list. An endpoint that exists in the schema SHALL appear in the executed checks
without a manual step to add it.

#### Scenario: A new endpoint is added to the API
- **WHEN** a new DRF view is exposed via a URL and therefore appears in the OpenAPI schema
- **THEN** the next conformance run includes a check against that endpoint without any change to
  the pipeline's own configuration

#### Scenario: An endpoint is removed from the API
- **WHEN** an endpoint is removed and no longer appears in the OpenAPI schema
- **THEN** the next conformance run no longer attempts to check it

### Requirement: Source expected behaviour from the capability specs
The system SHALL determine what a valid response looks like from the requirements in
`openspec/specs/<capability>/spec.md`, not from hand-guessed behaviour. Every assertion SHALL
cite the exact `### Requirement:` name it verifies.

#### Scenario: An assertion is added for an endpoint
- **WHEN** a contributor adds a check for an endpoint's behaviour
- **THEN** the check names the specific requirement in that capability's spec it verifies, and
  that name matches an existing `### Requirement:` heading exactly

### Requirement: Keep endpoint coverage and behavioural assertions as independent inputs
The system SHALL treat "which endpoints exist" (from the OpenAPI schema) and "how they should
behave" (from the specs) as independently maintained inputs that are combined only at execution
time. Adding or changing a behavioural assertion SHALL NOT require editing generated endpoint
coverage, and adding an endpoint SHALL NOT require editing the behavioural assertions.

#### Scenario: A requirement changes without any endpoint being added or removed
- **WHEN** a capability spec's requirement changes and its assertion is updated to match
- **THEN** no generated endpoint-coverage artifact needs to be hand-edited for that update to
  take effect

### Requirement: Document requirements that cannot be checked over HTTP
The system SHALL maintain an explicit, documented list of requirements that cannot be verified
by an HTTP request/response check (for example: behaviour that depends on reading outbound
email content, true concurrency, or a real-time wait), each with a stated reason. A requirement
with no assertion and no entry in this list is treated as an undocumented gap.

#### Scenario: A requirement cannot be verified over HTTP
- **WHEN** a requirement's verification would require inspecting something outside the HTTP
  response (e.g. the content of an email the API sends)
- **THEN** it is recorded in the documented out-of-scope list with a one-line reason, rather than
  silently having no assertion

### Requirement: Execute checks against a live instance of the API
The system SHALL run its checks as real HTTP requests against a running instance of the API, not
against mocked responses or the in-process Django test client.

#### Scenario: A conformance run executes
- **WHEN** the conformance workflow runs
- **THEN** it starts a live instance of the API and sends the checks to it over HTTP, observing
  actual responses

### Requirement: Fail the run when a live endpoint violates a requirement
The system SHALL fail the conformance run when any executed check's assertion does not hold
against the live response, and SHALL report which requirement the failing assertion was
verifying.

#### Scenario: A live endpoint's response violates a spec requirement
- **WHEN** an endpoint's actual response does not satisfy an assertion derived from a
  requirement
- **THEN** the conformance run fails, and its output names the requirement that was violated

#### Scenario: Every executed check's assertions hold
- **WHEN** every assertion against every checked endpoint holds
- **THEN** the conformance run succeeds

### Requirement: Run automatically after every merge to main
The system SHALL run the conformance checks automatically whenever a merge lands on `main`,
without requiring a person to trigger it manually.

#### Scenario: A pull request is merged into main
- **WHEN** a merge lands on `main`
- **THEN** the conformance workflow runs against the resulting API automatically

### Requirement: Keep the merge-time pass/fail gate deterministic
The system's merge-time pass/fail result SHALL be produced by deterministic execution of the
committed assertions, not by a live model evaluation performed during that run. A model MAY be
used to author or review the assertion library itself, as a separate, reviewed step before those
assertions are committed, but SHALL NOT itself decide the outcome of an automated run.

#### Scenario: A conformance run executes on a merge to main
- **WHEN** the conformance workflow runs after a merge
- **THEN** its pass/fail outcome is determined entirely by whether the committed, previously
  reviewed assertions hold against the live responses, with no model call made during that run

#### Scenario: An assertion is authored or changed
- **WHEN** a contributor adds or updates an assertion in the library
- **THEN** that assertion is reviewed (by a human, optionally assisted by a model) before it is
  committed and becomes part of what an automated run checks
