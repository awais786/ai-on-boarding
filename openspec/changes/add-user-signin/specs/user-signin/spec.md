## Purpose

Lets a registered person sign in with their email and password and receive a token they can use
on later requests, without ever revealing to a caller whether a failed attempt was due to a
wrong password or an unregistered email.

## ADDED Requirements

### Requirement: Accept a signin submission
The system SHALL accept a signin submission containing an email address and a password.

#### Scenario: Valid fields present
- **WHEN** a request is submitted with a non-empty email and a non-empty password
- **THEN** the submission proceeds to authentication

### Requirement: Reject a missing email
The system SHALL reject a signin submission in which the email address is absent or empty.

#### Scenario: Email omitted
- **WHEN** signin is submitted without an email field
- **THEN** the request is rejected and the response names the email field

### Requirement: Reject a missing password
The system SHALL reject a signin submission in which the password is absent or empty.

#### Scenario: Password omitted
- **WHEN** signin is submitted without a password field
- **THEN** the request is rejected and the response names the password field

### Requirement: Authenticate against the matching account
The system SHALL authenticate a signin submission against the stored credentials for the account
matching the submitted email, compared case-insensitively.

#### Scenario: Case-insensitive email match
- **WHEN** an account is registered under a lowercase email and signin is submitted with a
  different capitalisation of the same address and the correct password
- **THEN** authentication succeeds

### Requirement: Succeed with correct credentials
A signin submission with a registered email and its correct password SHALL succeed and return an
authentication token.

#### Scenario: Correct credentials
- **WHEN** the submitted email is registered and the password matches
- **THEN** the request succeeds

#### Scenario: Repeated signin with the same credentials
- **WHEN** the same correct credentials are submitted a second time
- **THEN** signin succeeds again

### Requirement: Signal success with an authentication token
A successful signin SHALL return HTTP 200 with a response body containing an opaque
authentication token, keyed `token`.

#### Scenario: Successful response shape
- **WHEN** signin succeeds
- **THEN** the response is HTTP 200 with a body of the form `{"token": "<opaque value>"}`

### Requirement: Reject an unregistered email
A signin submission with an email that is not registered SHALL be rejected.

#### Scenario: No account for the email
- **WHEN** the submitted email has no matching account
- **THEN** the request is rejected

### Requirement: Reject an incorrect password
A signin submission with a registered email and an incorrect password SHALL be rejected.

#### Scenario: Wrong password
- **WHEN** the submitted email is registered but the password does not match
- **THEN** the request is rejected

### Requirement: Reject all failure modes identically
A rejected signin SHALL return an identical response - same status, same body - whether the
email was unregistered, the password was wrong, or the email is currently locked out. A caller
MUST NOT be able to distinguish any of the three from the response alone.

#### Scenario: Unregistered email and wrong password are indistinguishable
- **WHEN** signin is attempted with an unregistered email, and separately with a registered
  email and the wrong password
- **THEN** both responses are identical in status and body

#### Scenario: Lockout is indistinguishable from a wrong password
- **WHEN** signin is attempted against an email currently locked out
- **THEN** the response is identical in status and body to a wrong-password rejection

### Requirement: Return HTTP 401 on rejection
A rejected signin SHALL return HTTP 401.

#### Scenario: Rejection status code
- **WHEN** signin is rejected for any reason
- **THEN** the response status is 401

### Requirement: Never return the password
The system SHALL NOT include the password, in any form, in any signin response.

#### Scenario: Password absent from every response
- **WHEN** any signin request is made, successful or not
- **THEN** the response body does not contain the submitted password in any form

### Requirement: Lock an email out after repeated failures
After 3 failed signin attempts against the same email within a 5-minute window, the system SHALL
reject further signin attempts against that email for 30 minutes, even if the correct password
is supplied during that period.

#### Scenario: Third failure triggers lockout
- **WHEN** 3 signin attempts against the same email fail within a 5-minute window
- **THEN** a fourth attempt with the correct password is still rejected

#### Scenario: Lockout expires
- **WHEN** 30 minutes have passed since the lockout began
- **THEN** a signin attempt with the correct password succeeds

### Requirement: Reset the failure count on success
A successful signin SHALL reset the failed-attempt count for that email to zero.

#### Scenario: Success clears prior failures
- **WHEN** an email has 1 or 2 recorded failures (below the lockout threshold) and then signs in
  successfully
- **THEN** the failure count for that email is reset to zero
