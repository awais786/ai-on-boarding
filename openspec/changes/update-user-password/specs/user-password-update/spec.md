## Purpose

Lets an authenticated caller change a password while signed in: their own, with proof of the
current password, or - if they are staff - any account's, without needing that account's
current password.

## ADDED Requirements

### Requirement: Require authentication
The system SHALL reject a password update request from a caller who is not authenticated.

#### Scenario: Unauthenticated request rejected
- **WHEN** a password update is requested with no valid authentication credential
- **THEN** the request is rejected with HTTP 401

### Requirement: Identify the target account
A password update request SHALL identify the account whose password is to be changed.

#### Scenario: Target account identified
- **WHEN** a password update is requested for an existing account
- **THEN** the request proceeds against that account

#### Scenario: Nonexistent target account
- **WHEN** a password update is requested naming an account that does not exist
- **THEN** the request is rejected with HTTP 404

### Requirement: A caller may update their own password
An authenticated caller SHALL be permitted to update the password of their own account.

#### Scenario: Caller targets their own account
- **WHEN** an authenticated caller requests a password update naming their own account
- **THEN** the request is permitted to proceed to validation

### Requirement: A non-staff caller may not update another account's password
A caller who is not staff SHALL be rejected when the account named in the request is not their
own.

#### Scenario: Non-staff caller targets a different account
- **WHEN** an authenticated, non-staff caller requests a password update naming an account other
  than their own
- **THEN** the request is rejected with HTTP 403 and the password of the named account is
  unchanged

### Requirement: A staff caller may update any account's password
A caller who is staff SHALL be permitted to update the password of any account, including one
other than their own.

#### Scenario: Staff caller targets another account
- **WHEN** an authenticated, staff caller requests a password update naming an account other than
  their own
- **THEN** the request is permitted to proceed to validation

### Requirement: Self-service update requires the current password
When the account named in the request is the caller's own, the request SHALL include the
account's current password, and the request SHALL be rejected if that current password does not
match.

#### Scenario: Current password omitted
- **WHEN** a caller requests a password update naming their own account, without a current
  password field
- **THEN** the request is rejected and the response names the current-password field

#### Scenario: Current password incorrect
- **WHEN** a caller requests a password update naming their own account, with a current password
  that does not match the account's stored password
- **THEN** the request is rejected and the account's password is unchanged

#### Scenario: Current password correct
- **WHEN** a caller requests a password update naming their own account, with the correct current
  password and an acceptable new password
- **THEN** the request succeeds

### Requirement: An admin-issued update does not require the target's current password
When a staff caller updates an account other than their own, the request SHALL succeed without
supplying that account's current password.

#### Scenario: Staff update with no current password
- **WHEN** a staff caller requests a password update naming another account, supplying only an
  acceptable new password
- **THEN** the request succeeds

### Requirement: Reject a request with no new password
The system SHALL reject a password update request in which the new password is absent or empty.

#### Scenario: New password omitted
- **WHEN** a password update is requested without a new-password field
- **THEN** the request is rejected and the response names the new-password field

### Requirement: Hold the new password to the signup strength rule
A new password supplied to a password update SHALL be subject to the same strength rule the
system applies when an account is created.

#### Scenario: Weak new password is rejected
- **WHEN** a password update is requested with a new password that signup would have rejected
- **THEN** the request is rejected, the response names the new-password field, and the account's
  password is unchanged

### Requirement: Signal success with HTTP 200 and no body content about the password
A successful password update SHALL return HTTP 200 and SHALL NOT include a password, in any
form, in the response body.

#### Scenario: Successful response shape
- **WHEN** a password update succeeds
- **THEN** the response is HTTP 200 and its body contains no password

### Requirement: Never return a password
The system SHALL NOT include a password, in any form, in any response from this endpoint,
whether the request succeeds or is rejected.

#### Scenario: Password absent from a rejected response
- **WHEN** a password update is rejected for any reason
- **THEN** the response body does not contain either submitted password in any form

### Requirement: The account authenticates with the new password
Once a password update succeeds, the account SHALL thereafter authenticate with the new password
and no longer with the one it had before.

#### Scenario: New password works, old one does not
- **WHEN** a password update succeeds
- **THEN** the account authenticates with the new password and no longer with its previous one

### Requirement: Invalidate existing authentication tokens on update
A successful password update SHALL invalidate every authentication token the target account
already holds, so a token issued before the update can no longer be used.

#### Scenario: Pre-existing token stops working
- **WHEN** an account holds an authentication token and its password is then successfully
  updated
- **THEN** the token the account held beforehand is no longer valid

#### Scenario: An admin update invalidates the target's tokens, not the admin's own
- **WHEN** a staff caller successfully updates another account's password
- **THEN** the tokens held by the updated account are invalidated and the staff caller's own
  token is unaffected
