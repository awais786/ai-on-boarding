## Purpose

Lets a caller holding a verified Google access token obtain the app's existing authentication
token, so a Google-authenticated MCP session can act against the API without the app ever
handling a Google OAuth code exchange itself or introducing a second kind of token.

## ADDED Requirements

### Requirement: Accept a Google access token submission
The system SHALL accept a submission containing a Google access token and attempt to
authenticate the caller from it.

#### Scenario: Token field present
- **WHEN** a request is submitted with a non-empty Google access token
- **THEN** the submission proceeds to verification

#### Scenario: Token field missing
- **WHEN** a request is submitted without a Google access token
- **THEN** the request is rejected and the response names the missing field

### Requirement: Verify the token with Google before trusting it
The system SHALL independently verify a submitted Google access token with Google - rather than
trusting any claim in the submission itself - before authenticating the caller.

#### Scenario: Token invalid or expired
- **WHEN** Google reports that the submitted access token is invalid, malformed, or expired
- **THEN** authentication is rejected and no application token is returned

### Requirement: Reject a token issued to an unrecognised audience
The system SHALL reject a Google access token whose audience is not on a configured allowlist of
accepted Google OAuth client IDs.

#### Scenario: Audience not on the allowlist
- **WHEN** a Google access token is otherwise valid but was issued for a client ID that is not on
  the configured allowlist
- **THEN** authentication is rejected and no application token is returned

#### Scenario: Audience on the allowlist
- **WHEN** a Google access token was issued for a client ID that is on the configured allowlist
- **THEN** this requirement does not block authentication

### Requirement: Reject an unverified email
The system SHALL reject a Google access token whose associated email address Google reports as
not verified.

#### Scenario: Email not verified
- **WHEN** a Google access token is otherwise valid but Google reports the associated email as
  not verified
- **THEN** authentication is rejected and no application token is returned

### Requirement: Reject a token outside the configured domain allowlist
Where the deployment configures an allowlist of accepted hosted domains, the system SHALL reject
a Google access token whose hosted domain (`hd`) is not on that allowlist. Where no domain
allowlist is configured, the system SHALL NOT reject a token on the basis of its hosted domain.

#### Scenario: Domain allowlist configured and not matched
- **WHEN** a domain allowlist is configured and a Google access token is otherwise valid but its
  hosted domain is absent or not on that allowlist
- **THEN** authentication is rejected and no application token is returned

#### Scenario: Domain allowlist configured and matched
- **WHEN** a domain allowlist is configured and a Google access token's hosted domain is on that
  allowlist
- **THEN** this requirement does not block authentication

#### Scenario: No domain allowlist configured
- **WHEN** no domain allowlist is configured
- **THEN** a Google access token is not rejected on the basis of its hosted domain, regardless of
  whether one is present

### Requirement: Map a verified Google identity to its Django account
Once a Google access token passes verification, the system SHALL identify the caller's Django
account from the token's Google account identifier (`sub`), independent of whether the
associated email address has since changed.

#### Scenario: Previously-linked Google identity
- **WHEN** a verified Google access token's account identifier was linked to a Django account on
  an earlier successful authentication
- **THEN** the caller is authenticated as that same Django account, even if the email address on
  the Google account has since changed

### Requirement: Reject a verified identity with no linked or matching account
The system SHALL reject a verified Google access token if its account identifier has no existing
link to a Django account and its verified email does not match any existing Django account. The
system SHALL NOT create a Django account as part of this authentication.

#### Scenario: No existing account for a first-time Google identity
- **WHEN** a verified Google access token has no prior link to a Django account and its verified
  email matches no existing account
- **THEN** authentication is rejected, no Django account is created, and no application token is
  returned

### Requirement: First successful authentication links the identity
The system SHALL persist a link between a verified Google access token's account identifier and
the matching Django account the first time that identifier successfully authenticates against an
account found by verified email.

#### Scenario: First-time Google login to an existing account
- **WHEN** a verified Google access token's account identifier has no prior link, but its
  verified email matches an existing Django account
- **THEN** authentication succeeds against that account and the identifier is linked to it for
  future authentications

### Requirement: Reject an embargoed account
The system SHALL reject authentication for a Google identity that maps to a Django account
subject to the existing embargo rule, on the same basis the existing password-based signin
flow already applies.

#### Scenario: Mapped account is embargoed
- **WHEN** a verified Google access token maps to a Django account that the embargo rule
  currently blocks
- **THEN** authentication is rejected and no application token is returned

### Requirement: Issue the existing application token on success
On successful authentication, the system SHALL return the same kind of authentication token
issued by the existing signin flow, and SHALL NOT return the caller's Google access token or any
field not already part of that existing token response.

#### Scenario: Successful Google authentication
- **WHEN** a Google access token passes verification and is mapped to a Django account
- **THEN** the response contains that account's application authentication token and nothing
  else identifying the Google account
