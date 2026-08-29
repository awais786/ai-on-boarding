## MODIFIED Requirements

### Requirement: Accept a signup submission
The system SHALL accept a signup submission containing an email address, a password, and a
country.

#### Scenario: Valid fields present
- **WHEN** a request is submitted with a non-empty email, a non-empty password, and a non-empty
  country
- **THEN** the submission proceeds to validation

## ADDED Requirements

### Requirement: Reject a missing country
The system SHALL reject a signup submission in which the country is absent or empty.

#### Scenario: Country omitted
- **WHEN** signup is submitted without a country field
- **THEN** the request is rejected and the response names the country field

### Requirement: Reject a submission from a blocked country
The system SHALL reject a signup submission whose country is currently on the blocked list.

#### Scenario: Blocked country rejected
- **WHEN** signup is submitted with a country that is currently blocked - for example, India
- **THEN** the request is rejected and the response names the country field

#### Scenario: Unblocked country allowed
- **WHEN** signup is submitted with a country that is not currently blocked
- **THEN** the submission proceeds and is not rejected for its country
