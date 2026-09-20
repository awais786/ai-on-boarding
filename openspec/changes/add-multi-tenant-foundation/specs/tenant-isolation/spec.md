## ADDED Requirements

### Requirement: Take the tenant from the credential, never from client input
For every request authenticated by a token, the system SHALL determine the organization from the
account the token belongs to. It SHALL ignore any organization named in the request's body,
query string, path or headers when deciding whose data the request may see or change.

#### Scenario: Naming another organization has no effect
- **WHEN** a signed-in user sends an authenticated request that also names a different
  organization in its body, query string or a header
- **THEN** the request behaves exactly as it would without that mention, scoped to the user's own
  organization

### Requirement: Refuse a token whose user is inactive
The system SHALL refuse every request authenticated by a token whose account has been
deactivated, including a token issued before the account was deactivated.

#### Scenario: Deactivated user with an existing token
- **WHEN** a user is deactivated after being issued a token, and then makes an authenticated
  request with that token
- **THEN** the request is refused as unauthenticated

### Requirement: Refuse a token whose organization is inactive
The system SHALL refuse every request authenticated by a token whose organization has been
deactivated, including a token issued before the organization was deactivated, and SHALL accept
the same token again once the organization is reactivated.

#### Scenario: Deactivated organization with an existing token
- **WHEN** an organization is deactivated after one of its users was issued a token, and that user
  then makes an authenticated request with the token
- **THEN** the request is refused as unauthenticated

#### Scenario: Reactivated organization
- **WHEN** the organization is reactivated and the same token is used again
- **THEN** the request is accepted

### Requirement: Refuse a token that has no organization
The system SHALL refuse a token-authenticated request from an account that belongs to no
organization, such as an operator account created outside signup.

#### Scenario: Account outside every organization
- **WHEN** an account with no organization presents a valid token to a protected endpoint
- **THEN** the request is refused as unauthenticated

### Requirement: Scope the user list to the caller's organization
The user list SHALL contain only users of the organization of the admin who requests it, and
SHALL apply the existing country and username filters within that organization only.

#### Scenario: Other organizations' users are absent
- **WHEN** an admin of one organization requests the user list while another organization also
  has users
- **THEN** the response contains only users of the admin's own organization

#### Scenario: A filter cannot reach across organizations
- **WHEN** an admin filters the list by a username or country that matches only a user of a
  different organization
- **THEN** the response is empty

### Requirement: Scope admin password changes to the caller's organization
An admin SHALL be able to change the password only of a user in the admin's own organization. A
username belonging only to another organization SHALL be answered exactly as a username that
exists nowhere, and SHALL leave that other user's password and tokens untouched.

#### Scenario: Admin changes a password within their own organization
- **WHEN** an admin of an organization changes the password of a user in that organization
- **THEN** the password is changed

#### Scenario: Admin targets a user of another organization
- **WHEN** an admin names a username that exists only in a different organization
- **THEN** the response is identical in status and body to one for a username that exists nowhere,
  and the other user's password and tokens are unchanged

### Requirement: Never reveal another organization through a response
No response to an authenticated request SHALL contain, or differ in a way that reveals, any
information about a user or organization other than the caller's own.

#### Scenario: Cross-organization and nonexistent look the same
- **WHEN** an authenticated caller refers to a user of another organization, and separately to a
  user that exists nowhere
- **THEN** the two responses are identical in status and body

### Requirement: Refuse a Google sign-in for an inactive organization
A Google sign-in that resolves to an account SHALL be refused, with the same response as any
other unusable account, when that account is inactive or its organization is inactive, and SHALL
still be refused when the verified address matches accounts in more than one organization.

#### Scenario: Inactive organization
- **WHEN** a verified Google address matches an account whose organization is inactive
- **THEN** no token is issued and the response is the same as for an address with no account

#### Scenario: Address shared across organizations
- **WHEN** a verified Google address matches accounts in two organizations
- **THEN** no token is issued
