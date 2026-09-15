## REMOVED Requirements

### Requirement: Refuse a caller this project will not sign in
**Reason**: Django's own sign-in endpoint answers identically (same status, same body) whether a
Google identity matches no account or matches an embargoed one, so this system cannot tell the
two apart to refuse only one of them. Both cases are now handled the same way: admitted to a
session with no session credential, rather than refused outright.
**Migration**: See "Admit a caller with no matching account, without a session credential" and
"Refuse a tool call made without a session credential" below - a caller this project will not
issue a credential to now reaches no data because no tool but signup will run for them, not
because the session itself was refused.

## ADDED Requirements

### Requirement: Admit a caller with no matching account, without a session credential
When a caller's Google access token is one Google recognises but the project issues no
credential for it - no account matches, or the matching one is embargoed - the system SHALL
admit the caller to an MCP session with no session credential, rather than refusing them
outright.

#### Scenario: No matching account
- **WHEN** a caller signs in with Google but the project has no account for that address
- **THEN** the caller's MCP session is established with no session credential, and no exchange
  for one is attempted

#### Scenario: Embargoed account
- **WHEN** a caller signs in with Google and their matching account is embargoed
- **THEN** the caller's MCP session is established with no session credential, the same as a
  caller with no matching account at all

### Requirement: Refuse a tool call made without a session credential
The system SHALL refuse any tool call that requires a session credential when the caller's
session has none, and SHALL tell the caller they need to sign up.

#### Scenario: A tool requiring a credential is called without one
- **WHEN** a caller with no session credential calls a tool other than the one that creates an
  account
- **THEN** the call is refused and the caller is told to sign up

#### Scenario: Signing up establishes a session credential
- **WHEN** a caller with no session credential successfully creates an account
- **THEN** their session gains a session credential, without a new MCP session being required

#### Scenario: An embargoed caller's signup attempt does not succeed
- **WHEN** a caller with no session credential whose account is actually embargoed (not
  accountless) calls the account-creation tool
- **THEN** the call fails as an ordinary duplicate-email/username refusal, and the caller's
  session still has no credential afterward
