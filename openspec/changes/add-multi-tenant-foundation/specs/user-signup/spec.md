## MODIFIED Requirements

### Requirement: Accept a signup submission
The system SHALL accept a signup submission containing an organization slug, that organization's
join code, an email address, a username, and a password.

#### Scenario: Valid fields present
- **WHEN** a request is submitted with a non-empty organization, join code, email, username, and
  password
- **THEN** the submission proceeds to validation

### Requirement: Reject a duplicate email
The system SHALL reject a signup submission whose (normalised) email address is already
registered in the named organization, including when two submissions for the same email into the
same organization race each other. An email registered only in a different organization is not a
duplicate.

#### Scenario: Email already registered
- **WHEN** signup is submitted into an organization with an email that already has an account in
  that organization
- **THEN** the request is rejected, the response names the email field, and no second account
  is created

#### Scenario: Email registered only in another organization
- **WHEN** signup is submitted into an organization with an email that has an account only in a
  different organization
- **THEN** the signup succeeds

#### Scenario: Concurrent signups for the same email
- **WHEN** two signup requests for the same email into the same organization are submitted
  concurrently
- **THEN** exactly one succeeds and the other is rejected with the same field-keyed response as
  an ordinary duplicate - never an unhandled server error

### Requirement: Reject a duplicate username
The system SHALL reject a signup submission whose (normalised) username is already registered in
the named organization, including when two submissions for the same username into the same
organization race each other. A username registered only in a different organization is not a
duplicate.

#### Scenario: Username already registered
- **WHEN** signup is submitted into an organization with a username that already has an account
  in that organization
- **THEN** the request is rejected, the response names the username field, and no second account
  is created

#### Scenario: Username registered only in another organization
- **WHEN** signup is submitted into an organization with a username that has an account only in a
  different organization
- **THEN** the signup succeeds

#### Scenario: Concurrent signups for the same username
- **WHEN** two signup requests for the same username into the same organization are submitted
  concurrently
- **THEN** exactly one succeeds and the other is rejected with the same field-keyed response as
  an ordinary duplicate - never an unhandled server error

## ADDED Requirements

### Requirement: Reject a missing organization
The system SHALL reject a signup submission in which the organization is absent or empty.

#### Scenario: Organization omitted
- **WHEN** signup is submitted without an organization field
- **THEN** the request is rejected and the response names the organization field

### Requirement: Reject a missing join code
The system SHALL reject a signup submission in which the join code is absent or empty.

#### Scenario: Join code omitted
- **WHEN** signup is submitted without a join code field
- **THEN** the request is rejected and the response names the join code field

### Requirement: Admit a signup only with the organization's join code
The system SHALL create an account in an organization only when the submission names that
organization and presents its current join code. The account SHALL be created in the organization
named, and a caller MUST NOT be able to place an account in an organization whose join code they
do not hold.

#### Scenario: Correct organization and join code
- **WHEN** a valid signup names an active organization and presents its current join code
- **THEN** the account is created and belongs to that organization

#### Scenario: Wrong join code
- **WHEN** a signup names an active organization but presents a join code that is not its current
  code
- **THEN** the request is rejected and no account is created

#### Scenario: Another organization's join code
- **WHEN** a signup names one organization but presents the join code of a different
  organization
- **THEN** the request is rejected and no account is created in either

#### Scenario: Join code that has been rotated away
- **WHEN** a signup presents a join code that an operator has since rotated away
- **THEN** the request is rejected

### Requirement: Refuse an unknown, inactive or wrongly-coded organization identically
A signup rejected because the organization does not exist, is inactive, has no join code issued,
or was given the wrong join code SHALL return an identical response - same status, same body,
naming the join code field. A caller MUST NOT be able to tell these four cases apart, and so MUST
NOT be able to discover which organizations exist.

#### Scenario: Four causes are indistinguishable
- **WHEN** signup is attempted with an unknown organization, with an inactive organization, with
  an organization that has no join code issued, and with a real organization and a wrong join
  code
- **THEN** all four responses are identical in status and body

### Requirement: Never return the join code
The system SHALL NOT include the join code, in any form, in any signup response - success or
rejection.

#### Scenario: Join code absent from every response
- **WHEN** any signup request is made, successful or not
- **THEN** the response body does not contain the submitted join code
