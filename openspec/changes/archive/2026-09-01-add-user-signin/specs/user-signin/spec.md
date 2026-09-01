## MODIFIED Requirements

### Requirement: Accept a signin submission
The system SHALL accept a signin submission containing an email or username - submitted as a
single field, keyed `email_or_username` - and a password.

#### Scenario: Valid fields present
- **WHEN** a request is submitted with a non-empty email or username and a non-empty password
- **THEN** the submission proceeds to authentication

### Requirement: Reject a missing email
The system SHALL reject a signin submission in which the `email_or_username` field is absent or
empty.

#### Scenario: Email or username omitted
- **WHEN** signin is submitted without an `email_or_username` field
- **THEN** the request is rejected and the response names the `email_or_username` field

### Requirement: Authenticate against the matching account
The system SHALL authenticate a signin submission against the stored credentials for the account
whose email or username matches the submitted value, compared case-insensitively.

#### Scenario: Case-insensitive email match
- **WHEN** an account is registered under a lowercase email and signin is submitted with a
  different capitalisation of the same address and the correct password
- **THEN** authentication succeeds

#### Scenario: Case-insensitive username match
- **WHEN** an account is registered under a lowercase username and signin is submitted with a
  different capitalisation of the same username and the correct password
- **THEN** authentication succeeds

### Requirement: Succeed with correct credentials
A signin submission with a registered email or username and its correct password SHALL succeed
and return an authentication token.

#### Scenario: Correct credentials
- **WHEN** the submitted email or username is registered and the password matches
- **THEN** the request succeeds

#### Scenario: Repeated signin with the same credentials
- **WHEN** the same correct credentials are submitted a second time
- **THEN** signin succeeds again

### Requirement: Reject an unregistered email
A signin submission whose `email_or_username` value (an email or a username) matches no account
SHALL be rejected.

#### Scenario: No account for the email or username
- **WHEN** the submitted value matches neither an email nor a username on any account
- **THEN** the request is rejected

### Requirement: Reject an incorrect password
A signin submission with a registered email or username and an incorrect password SHALL be
rejected.

#### Scenario: Wrong password
- **WHEN** the submitted email or username is registered but the password does not match
- **THEN** the request is rejected

### Requirement: Reject all failure modes identically
A rejected signin SHALL return an identical response - same status, same body - whether the
email or username was unregistered, the password was wrong, or the account is currently locked
out. A caller MUST NOT be able to distinguish any of the three from the response alone.

#### Scenario: Unregistered email and wrong password are indistinguishable
- **WHEN** signin is attempted with an unregistered email or username, and separately with a
  registered one and the wrong password
- **THEN** both responses are identical in status and body

#### Scenario: Lockout is indistinguishable from a wrong password
- **WHEN** signin is attempted against an account currently locked out
- **THEN** the response is identical in status and body to a wrong-password rejection

### Requirement: Lock an email out after repeated failures
After 3 failed signin attempts against the same account within a 5-minute window, the system
SHALL reject further signin attempts against that account for 30 minutes, even if the correct
password is supplied during that period, and regardless of whether each attempt used the
account's email or its username. An email or username that matches no account SHALL be
rate-limited the same way, keyed on the submitted value itself.

#### Scenario: Third failure triggers lockout
- **WHEN** 3 signin attempts against the same account fail within a 5-minute window
- **THEN** a fourth attempt with the correct password is still rejected

#### Scenario: Lockout applies across email and username
- **WHEN** an account accumulates 3 failed attempts within a 5-minute window, using a mix of its
  email and its username across those attempts
- **THEN** a further attempt against that account, using either its email or its username, is
  still rejected

#### Scenario: Lockout expires
- **WHEN** 30 minutes have passed since the lockout began
- **THEN** a signin attempt with the correct password succeeds

### Requirement: Reset the failure count on success
A successful signin SHALL reset the failed-attempt count for that account to zero.

#### Scenario: Success clears prior failures
- **WHEN** an account has 1 or 2 recorded failures (below the lockout threshold) and then signs
  in successfully
- **THEN** the failure count for that account is reset to zero
