## MODIFIED Requirements

### Requirement: Accept a signup submission
The system SHALL accept a signup submission containing an email address, a username, and a
password.

#### Scenario: Valid fields present
- **WHEN** a request is submitted with a non-empty email, a non-empty username, and a non-empty
  password
- **THEN** the submission proceeds to validation

### Requirement: Signal success with the created account's email
A successful signup SHALL return HTTP 200 with a response body containing the created account's
email address and username, and nothing else.

#### Scenario: Successful response shape
- **WHEN** signup succeeds
- **THEN** the response is HTTP 200 with a body containing only the email and username fields

## ADDED Requirements

### Requirement: Reject a missing username
The system SHALL reject a signup submission in which the username is absent or empty.

#### Scenario: Username omitted
- **WHEN** signup is submitted without a username field
- **THEN** the request is rejected and the response names the username field

### Requirement: Enforce a username format
The system SHALL reject a username that is not 3-30 characters long, or that contains any
character other than a letter, a digit, or an underscore.

#### Scenario: Username too short or too long
- **WHEN** signup is submitted with a username under 3 characters or over 30 characters
- **THEN** the request is rejected and the response names the username field

#### Scenario: Username contains a disallowed character
- **WHEN** signup is submitted with a username containing a character that is not a letter, a
  digit, or an underscore
- **THEN** the request is rejected and the response names the username field

### Requirement: Reject a duplicate username
The system SHALL reject a signup submission whose (normalised) username is already registered,
including when two submissions for the same username race each other.

#### Scenario: Username already registered
- **WHEN** signup is submitted with a username that already has an account
- **THEN** the request is rejected, the response names the username field, and no second account
  is created

#### Scenario: Concurrent signups for the same username
- **WHEN** two signup requests for the same username are submitted concurrently
- **THEN** exactly one succeeds and the other is rejected with the same field-keyed response as
  an ordinary duplicate - never an unhandled server error

### Requirement: Normalise username to lowercase
The system SHALL normalise a username to lowercase before storing or comparing it, so two
accounts can never differ only by case, consistent with how email is normalised.

#### Scenario: Case-insensitive duplicate detection
- **WHEN** an account already exists for a username and a second signup is submitted for the
  same username with different capitalisation
- **THEN** the second submission is rejected as a duplicate

#### Scenario: Stored and returned username is lowercase
- **WHEN** signup succeeds with a mixed-case username
- **THEN** the stored username and the username in the success response are both lowercase
