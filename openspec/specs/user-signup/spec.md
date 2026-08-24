# user-signup Specification

## Purpose
Lets a person create an account by providing an email address, a username, and a password, so
they can subsequently sign in with either identifier.

## Requirements

### Requirement: Accept a signup submission
The system SHALL accept a signup submission containing an email address, a username, and a
password.

#### Scenario: Valid fields present
- **WHEN** a request is submitted with a non-empty email, a non-empty username, and a non-empty
  password
- **THEN** the submission proceeds to validation

### Requirement: Reject a missing email
The system SHALL reject a signup submission in which the email address is absent or empty.

#### Scenario: Email omitted
- **WHEN** signup is submitted without an email field
- **THEN** the request is rejected and the response names the email field

### Requirement: Reject a missing password
The system SHALL reject a signup submission in which the password is absent or empty.

#### Scenario: Password omitted
- **WHEN** signup is submitted without a password field
- **THEN** the request is rejected and the response names the password field

### Requirement: Reject a missing username
The system SHALL reject a signup submission in which the username is absent or empty.

#### Scenario: Username omitted
- **WHEN** signup is submitted without a username field
- **THEN** the request is rejected and the response names the username field

### Requirement: Reject an invalid email address
The system SHALL reject a signup submission whose email address is not a valid email address.

#### Scenario: Malformed email
- **WHEN** signup is submitted with a value that is not a syntactically valid email address
- **THEN** the request is rejected and the response names the email field

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

### Requirement: Reject a duplicate email
The system SHALL reject a signup submission whose (normalised) email address is already
registered, including when two submissions for the same email race each other.

#### Scenario: Email already registered
- **WHEN** signup is submitted with an email that already has an account
- **THEN** the request is rejected, the response names the email field, and no second account
  is created

#### Scenario: Concurrent signups for the same email
- **WHEN** two signup requests for the same email are submitted concurrently
- **THEN** exactly one succeeds and the other is rejected with the same field-keyed response as
  an ordinary duplicate - never an unhandled server error

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

### Requirement: Enforce a minimum password strength
The system SHALL reject a password shorter than 8 characters, or one that does not contain at
least one letter and at least one digit. No other composition rule applies.

#### Scenario: Password too short
- **WHEN** signup is submitted with a password under 8 characters
- **THEN** the request is rejected and the response names the password field

#### Scenario: Password missing a letter or a digit
- **WHEN** signup is submitted with a password of 8 or more characters that lacks a letter, or
  lacks a digit
- **THEN** the request is rejected and the response names the password field

### Requirement: Create exactly one account on a valid submission
On a valid submission, the system SHALL create exactly one account.

#### Scenario: Successful account creation
- **WHEN** a valid email and password are submitted
- **THEN** exactly one account exists afterward that did not exist before

### Requirement: Store the password unrecoverably
The system SHALL store the password in a form from which the original password cannot be
recovered.

#### Scenario: Password is hashed, not stored as plain text
- **WHEN** an account is created
- **THEN** the stored credential is not equal to the submitted password, and the submitted
  password can be verified against it

### Requirement: Never return the password
The system SHALL NOT include the password, in any form, in any signup response - success or
rejection.

#### Scenario: Password absent from every response
- **WHEN** any signup request is made, successful or not
- **THEN** the response body does not contain the submitted password in any form

### Requirement: Name the offending field on rejection
A signup rejection SHALL identify which field was unacceptable.

#### Scenario: Rejection names a field
- **WHEN** a signup submission is rejected for any reason
- **THEN** the response body identifies the specific field responsible

### Requirement: Signal success with the created account's email
A successful signup SHALL return HTTP 200 with a response body containing the created account's
email address and username, and nothing else.

#### Scenario: Successful response shape
- **WHEN** signup succeeds
- **THEN** the response is HTTP 200 with a body containing only the email and username fields

### Requirement: Normalise email to lowercase
The system SHALL normalise an email address to lowercase before storing or comparing it, so two
accounts can never differ only by case.

#### Scenario: Case-insensitive duplicate detection
- **WHEN** an account already exists for an email and a second signup is submitted for the same
  address with different capitalisation
- **THEN** the second submission is rejected as a duplicate

#### Scenario: Stored and returned email is lowercase
- **WHEN** signup succeeds with a mixed-case email
- **THEN** the stored email and the email in the success response are both lowercase

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
