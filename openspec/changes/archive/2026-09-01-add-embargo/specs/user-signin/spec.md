## MODIFIED Requirements

### Requirement: Reject all failure modes identically
A rejected signin SHALL return an identical response - same status, same body - whether the
email or username was unregistered, the password was wrong, the account is currently locked
out, or the account's country is currently blocked. A caller MUST NOT be able to distinguish any
of the four from the response alone.

#### Scenario: Unregistered email or username and wrong password are indistinguishable
- **WHEN** signin is attempted with an unregistered email or username, and separately with a
  registered one and the wrong password
- **THEN** both responses are identical in status and body

#### Scenario: Lockout is indistinguishable from a wrong password
- **WHEN** signin is attempted against an account currently locked out
- **THEN** the response is identical in status and body to a wrong-password rejection

#### Scenario: Embargo is indistinguishable from a wrong password
- **WHEN** signin is attempted against an account whose country is currently blocked
- **THEN** the response is identical in status and body to a wrong-password rejection

## ADDED Requirements

### Requirement: Reject signin for an embargoed account
The system SHALL reject a signin submission for an account whose country - as submitted at
signup - is currently on the blocked list, evaluated fresh at the time of the signin attempt.

#### Scenario: Country blocked after the account was created
- **WHEN** an account's country was allowed at signup and is later added to the blocked list
- **THEN** a subsequent signin attempt for that account, even with the correct password, is
  rejected

#### Scenario: Country unblocked after being blocked
- **WHEN** an account's country was blocked and is later removed from the blocked list
- **THEN** a subsequent signin attempt for that account with the correct password succeeds
