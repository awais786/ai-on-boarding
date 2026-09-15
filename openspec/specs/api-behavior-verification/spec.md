# api-behavior-verification Specification

## Purpose
Verifies that the running API's observable HTTP behaviour matches the requirements recorded in
`openspec/specs/`, with the set of exercised endpoints derived from the API's own OpenAPI
description so it cannot fall behind what is actually served, and with a merge to `main` reported
as failed when a specified behaviour no longer holds.

## Requirements

### Requirement: Run automatically on every push to main
The verification run SHALL start without manual action whenever a commit reaches `main`, and
SHALL also be startable on demand.

#### Scenario: A merge starts a run
- **WHEN** a commit reaches `main`, whether pushed directly or by merging a pull request
- **THEN** a verification run starts with no further action by any person

#### Scenario: A run can be started on demand
- **WHEN** a person asks for a verification run without pushing anything
- **THEN** a run starts against the current state of `main`

### Requirement: Derive endpoint coverage from the OpenAPI description
The endpoints exercised by a run SHALL be derived from the API's current OpenAPI description
rather than from a list maintained by hand.

#### Scenario: A new endpoint is exercised without changing the verification setup
- **WHEN** an endpoint is added, appears in the OpenAPI description, and nothing in the
  verification setup is changed
- **THEN** the next run exercises that endpoint

#### Scenario: A removed endpoint stops being exercised on its own
- **WHEN** an endpoint is removed and no longer appears in the OpenAPI description, and nothing
  in the verification setup is changed
- **THEN** the next run does not exercise it

### Requirement: Account for every address the application routes
Every address the application routes SHALL be either derived from the OpenAPI description,
declared as a surface carrying requirements that the description omits, or excluded with a
written reason. A run SHALL fail when an address is none of these, so that no HTTP surface is
left unverified without a deliberate, recorded decision.

#### Scenario: An unaccounted-for address fails the run
- **WHEN** the application routes an address that is neither present in the OpenAPI description,
  nor declared, nor excluded with a reason
- **THEN** the run fails and names that address

#### Scenario: A declared surface absent from the description is still exercised
- **WHEN** an address carries requirements in a promoted spec but does not appear in the OpenAPI
  description, and it is declared
- **THEN** the run exercises it alongside the derived endpoints

#### Scenario: An excluded address states why
- **WHEN** an address is excluded from verification
- **THEN** the exclusion records a reason, and the run does not fail on that address

### Requirement: Take expected behaviour from the promoted specs
What an endpoint is expected to do SHALL be determined by the requirements in
`openspec/specs/`, and not by expectations formed anywhere else. Every behavioural check SHALL
name the requirement it verifies.

#### Scenario: A check names its requirement
- **WHEN** a behavioural check is defined for an endpoint
- **THEN** it names a requirement that appears in a promoted capability spec

#### Scenario: Behaviour with no promoted requirement is not judged
- **WHEN** an endpoint behaves in a way that no promoted spec describes
- **THEN** the run does not fail on that behaviour

#### Scenario: A promoted requirement is picked up without changing the checks
- **WHEN** a capability's spec is promoted into `openspec/specs/` and nothing in the verification
  setup is changed
- **THEN** the next run's evaluation considers that capability's requirements

### Requirement: Check specified behaviour, not only a successful status
Where a spec states what a response must contain, must not contain, or how a request must be
refused, the run SHALL check that, and SHALL NOT treat a successful status code as sufficient.

#### Scenario: A refusal is checked as the spec states it
- **WHEN** a requirement states that a request meeting some condition is refused
- **THEN** the run sends a request meeting that condition and checks the refusal against what the
  requirement states, not merely that a response arrived

#### Scenario: A response body is checked against what the spec constrains
- **WHEN** a requirement constrains what a response body must or must not hold
- **THEN** the run checks the body against that constraint

#### Scenario: A forbidden value is checked for absence
- **WHEN** a requirement states that a value is never returned in a response
- **THEN** the run checks that responses do not carry it

### Requirement: Express a requirement spanning several requests as an ordered sequence
Where a requirement is only observable across more than one request, the run SHALL issue those
requests in order and judge the requirement against them together.

#### Scenario: Responses required to be indistinguishable are compared with each other
- **WHEN** a requirement states that two or more refusals cannot be told apart
- **THEN** the run obtains each refusal and compares them against each other, rather than
  checking each one alone

#### Scenario: A requirement about a later effect is checked after the earlier request
- **WHEN** a requirement states that one request changes how a later one is answered
- **THEN** the run issues them in that order and checks the later response

### Requirement: Reach a delivered reset code the way a recipient reaches it
Because a reset code is never returned in a response, the run SHALL obtain it from the message
delivered to the account holder in order to verify behaviour that depends on holding a usable
code. Obtaining it this way SHALL NOT weaken the requirement that no response carries it.

#### Scenario: The code is taken from the delivered message
- **WHEN** the run needs a usable reset code
- **THEN** it takes the code from the message delivered for that address

#### Scenario: The response is still checked for absence of the code
- **WHEN** the run obtains a code from a delivered message
- **THEN** it still checks that the response to the request that caused the delivery does not
  carry that code

### Requirement: Record requirements that cannot be observed from outside the process
A requirement, or an individual scenario within a requirement, that cannot be judged by observing
HTTP behaviour during a run SHALL be recorded by name, with the reason it cannot. A recorded entry
SHALL NOT fail a run, and SHALL NOT be reported as missing coverage. Recording one scenario SHALL
NOT excuse the other scenarios of the same requirement.

#### Scenario: An unobservable requirement is recorded with its reason
- **WHEN** a requirement cannot be judged from outside the process
- **THEN** it is recorded by name together with why it cannot be judged

#### Scenario: Recording one scenario leaves its siblings still required
- **WHEN** one scenario of a requirement is recorded as unobservable and another scenario of the
  same requirement can be judged from outside the process
- **THEN** the run still requires a check for the scenario that can be judged

#### Scenario: A recorded requirement does not fail the run
- **WHEN** a requirement is recorded as unobservable
- **THEN** the run neither fails on it nor reports it as lacking a check

#### Scenario: An unrecorded requirement with no check is not silently accepted
- **WHEN** a requirement has no check and is not recorded as unobservable
- **THEN** the run reports it

### Requirement: Execute the checks as a Postman collection
The derived endpoints and their attached checks SHALL be assembled into a Postman collection and
executed against a running instance of the API by a collection runner, producing a
machine-readable report.

#### Scenario: Every check produces a recorded outcome
- **WHEN** the collection is executed against a running instance
- **THEN** the report records, for each request, whether each check attached to it passed or
  failed

### Requirement: Fail the run when observed behaviour contradicts a requirement
The run SHALL fail when the running API answers a request in a way that a checked requirement
says it must not.

#### Scenario: A contradicted requirement fails the run
- **WHEN** a response does not satisfy a check
- **THEN** the run fails and names the requirement that check verifies

### Requirement: Evaluate the checks against the specs before a run may pass
A run SHALL include an automated evaluation of the checks and their results against the promoted
specs, covering at least: requirements with no check, checks that state something other than what
the requirement they name says, and endpoints checked only for a status code where their spec
states more.

#### Scenario: A requirement with no check is reported
- **WHEN** a promoted requirement applies to a verified endpoint, has no check, and is not
  recorded as unobservable
- **THEN** the evaluation reports it

#### Scenario: A check that misstates its requirement is reported
- **WHEN** a check verifies something other than what the requirement it names states
- **THEN** the evaluation reports it

#### Scenario: An endpoint checked only for a status code is reported
- **WHEN** an endpoint's spec states behaviour beyond a successful response, and that endpoint is
  checked only for a status code
- **THEN** the evaluation reports it

### Requirement: Fail the run on an evaluation finding that names a requirement
The run SHALL fail on an evaluation finding that names a requirement, unless that requirement is
recorded as unobservable. A finding that names no requirement SHALL be reported without failing
the run, matching the distinction this project already draws between a blocking finding and a
nit.

#### Scenario: A finding naming a requirement fails the run
- **WHEN** the evaluation reports a finding that names a promoted requirement not recorded as
  unobservable
- **THEN** the run fails and the named requirement appears in the run's output

#### Scenario: A finding naming no requirement does not fail the run
- **WHEN** the evaluation reports a finding that names no requirement
- **THEN** the finding appears in the run's output and the run does not fail on it

### Requirement: Fail rather than pass when the evaluation cannot be performed
When the evaluation cannot run, the run SHALL fail and say why. It SHALL NOT report success with
the evaluation skipped.

#### Scenario: A run without what the evaluation needs fails
- **WHEN** the evaluation cannot be performed because something it requires is unavailable
- **THEN** the run fails and reports what was unavailable

### Requirement: Document where coverage and expected behaviour come from
The repository SHALL carry documentation stating which part of this verification supplies the set
of endpoints, which part supplies expected behaviour, what executes the checks, what the
evaluation judges, and how a run decides to pass or fail - so that a contributor adding an
endpoint can tell what is expected of them without reading the tooling.

#### Scenario: A contributor can find where behavioural coverage comes from
- **WHEN** a contributor adds an endpoint and looks for what verification it needs
- **THEN** the documentation tells them coverage of the endpoint follows from the OpenAPI
  description, and that its expected behaviour comes from its capability's requirements

#### Scenario: The pass and fail conditions are written down
- **WHEN** a contributor asks why a verification run failed
- **THEN** the documentation states the conditions under which a run fails
