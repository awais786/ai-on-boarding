## Purpose

Defines the signup, forgot/reset-password, and self-service change-password tools this MCP
server exposes: what each takes, what a caller learns from calling it, and what it never
reveals.

## ADDED Requirements

### Requirement: Create an account
A caller with no session credential SHALL be able to create a Django account by supplying an
email, username, password, and country, subject to the same validation Django's own signup
applies (uniqueness, password strength, blocked countries).

#### Scenario: Successful signup
- **WHEN** a caller with no session credential supplies a valid, unused email and username, a
  password meeting the strength requirement, and a country that is not blocked
- **THEN** the account is created and the tool reports success

#### Scenario: Signup grants a session credential
- **WHEN** signup succeeds
- **THEN** the calling session gains a session credential usable by the other tools, without the
  caller reconnecting

#### Scenario: Duplicate email or username
- **WHEN** a caller supplies an email or username an account already uses
- **THEN** the tool refuses and no account is created

#### Scenario: Weak password
- **WHEN** a caller supplies a password that does not meet the strength requirement
- **THEN** the tool refuses and no account is created

#### Scenario: Blocked country
- **WHEN** a caller supplies a country signups are not allowed from
- **THEN** the tool refuses and no account is created

#### Scenario: A password is never returned
- **WHEN** a signup call succeeds or fails for any reason
- **THEN** the tool's result never contains the submitted password

### Requirement: Request a password-reset code
Any caller SHALL be able to request a password-reset code for an email address, and the tool's
result SHALL be identical whether or not that address has an account.

#### Scenario: Address has an account
- **WHEN** a caller requests a reset code for an email address that has an account
- **THEN** the tool reports the same outcome as for an address with no account, and a reset code
  is delivered to that address

#### Scenario: Address has no account
- **WHEN** a caller requests a reset code for an email address with no account
- **THEN** the tool reports the same outcome as for an address that has one, and nothing is
  delivered

### Requirement: Complete a password reset
A caller holding a valid reset code SHALL be able to set a new password with it, subject to the
same password-strength requirement used elsewhere. A code that is invalid, expired, or already
used SHALL be refused identically in every case.

#### Scenario: Valid code and a strong new password
- **WHEN** a caller supplies a valid, unused reset code and a new password meeting the strength
  requirement
- **THEN** the account's password is set to the new password and the tool reports success

#### Scenario: Invalid, expired, or already-used code
- **WHEN** a caller supplies a code that is invalid, expired, or already used
- **THEN** the tool refuses with the same outcome for all three cases, and no password changes

#### Scenario: Weak new password
- **WHEN** a caller supplies a valid code but a new password that does not meet the strength
  requirement
- **THEN** the tool refuses and no password changes

#### Scenario: A password is never returned
- **WHEN** a password-reset completion call succeeds or fails for any reason
- **THEN** the tool's result never contains the new password

### Requirement: Change the caller's own password
A caller with a session credential SHALL be able to change their own password by supplying their
current password and a new one; a caller with no session credential SHALL be refused and told to
sign up.

#### Scenario: Correct current password and a strong new password
- **WHEN** a caller with a session credential supplies their correct current password and a new
  password meeting the strength requirement
- **THEN** the account's password is set to the new password and the tool reports success

#### Scenario: Wrong current password
- **WHEN** a caller with a session credential supplies an incorrect current password
- **THEN** the tool refuses and the password is unchanged

#### Scenario: No session credential
- **WHEN** a caller with no session credential calls this tool
- **THEN** the tool refuses and tells the caller to sign up

#### Scenario: Neither password is ever returned
- **WHEN** a change-password call succeeds or fails for any reason
- **THEN** the tool's result never contains the current password or the new password
