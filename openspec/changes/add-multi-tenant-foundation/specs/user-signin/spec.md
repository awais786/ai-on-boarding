## MODIFIED Requirements

### Requirement: Accept a signin submission
The system SHALL accept a signin submission containing an organization slug, an email or
username - submitted as a single field, keyed `email_or_username` - and a password.

#### Scenario: Valid fields present
- **WHEN** a request is submitted with a non-empty organization, email or username, and password
- **THEN** the submission proceeds to authentication

### Requirement: Authenticate against the matching account
The system SHALL authenticate a signin submission against the stored credentials for the account,
within the named organization, whose email or username matches the submitted value, compared
case-insensitively.

#### Scenario: Case-insensitive email match
- **WHEN** an account is registered under a lowercase email and signin is submitted to its
  organization with a different capitalisation of the same address and the correct password
- **THEN** authentication succeeds

#### Scenario: Case-insensitive username match
- **WHEN** an account is registered under a lowercase username and signin is submitted to its
  organization with a different capitalisation of the same username and the correct password
- **THEN** authentication succeeds

#### Scenario: Same identifier in two organizations
- **WHEN** two organizations each hold an account with the same email and different passwords, and
  signin is submitted to each organization with that email and that organization's password
- **THEN** each signin succeeds and returns a token for its own organization's account

### Requirement: Reject all failure modes identically
A rejected signin SHALL return an identical response - same status, same body - whether the
organization was unknown or inactive, the email or username was unregistered in that
organization, the password was wrong, the account is inactive, or the account is currently locked
out. A caller MUST NOT be able to distinguish any of these from the response alone, including by
how long the response takes.

#### Scenario: Unregistered email or username and wrong password are indistinguishable
- **WHEN** signin is attempted with an unregistered email or username, and separately with a
  registered one and the wrong password
- **THEN** both responses are identical in status and body

#### Scenario: Lockout is indistinguishable from a wrong password
- **WHEN** signin is attempted against an account currently locked out
- **THEN** the response is identical in status and body to a wrong-password rejection

#### Scenario: Unknown organization is indistinguishable from a wrong password
- **WHEN** signin is attempted naming an organization that does not exist, and separately naming a
  real organization with the wrong password
- **THEN** both responses are identical in status and body

#### Scenario: Wrong organization is indistinguishable from a wrong password
- **WHEN** signin is attempted with the correct credentials of an account in one organization but
  naming a different real organization
- **THEN** the response is identical in status and body to a wrong-password rejection

#### Scenario: Every failure path costs the same as a real password check
- **WHEN** signin is rejected because the organization is unknown or inactive, the identifier is
  unregistered, or the account is locked out
- **THEN** the system has still paid for one password hash, so the response is not measurably
  faster than a rejection for a wrong password

#### Scenario: Inactive account or organization is indistinguishable
- **WHEN** signin is attempted with correct credentials for an inactive account, and separately
  for an account whose organization is inactive
- **THEN** both responses are identical in status and body to a wrong-password rejection

### Requirement: Lock an email out after repeated failures
After 3 failed signin attempts against the same account within a 5-minute window, the system
SHALL reject further signin attempts against that account for 30 minutes, even if the correct
password is supplied during that period, and regardless of whether each attempt used the
account's email or its username. An email or username that matches no account in the named
organization SHALL be rate-limited the same way, keyed on the organization and the submitted
value together. Failures in one organization MUST NOT count against, or lock out, an account
with the same email or username in another organization.

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

#### Scenario: Lockout does not cross organizations
- **WHEN** 3 signin attempts naming one organization fail for an email, and the same email exists
  in a second organization
- **THEN** signin to the second organization with its correct password still succeeds

## ADDED Requirements

### Requirement: Reject a missing organization
The system SHALL reject a signin submission in which the organization is absent or empty.

#### Scenario: Organization omitted
- **WHEN** signin is submitted without an organization field
- **THEN** the request is rejected and the response names the organization field

### Requirement: Issue a token bound to the account's organization
A successful signin SHALL return a token that authenticates as that account, and therefore in
that account's organization, and in no other.

#### Scenario: Token acts in its own organization only
- **WHEN** a user signs in to their organization and uses the token
- **THEN** every authenticated request made with it is scoped to that organization
