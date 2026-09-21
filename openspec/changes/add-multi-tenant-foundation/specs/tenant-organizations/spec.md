## ADDED Requirements

### Requirement: Describe an organization
The system SHALL record, for each organization, a name, a slug, a domain, the time it was created,
the time it was last changed, and whether it is active.

#### Scenario: A new organization is active
- **WHEN** an operator creates an organization
- **THEN** it has a name, a slug, a domain and creation and update timestamps, and is active

### Requirement: Give every organization a unique domain
The system SHALL give every organization exactly one domain - a bare host name, optionally with a
port, and no scheme or path - and SHALL NOT allow two organizations to share one.

#### Scenario: Duplicate domain refused
- **WHEN** an operator creates an organization whose domain another organization already has
- **THEN** creation is refused and no second organization exists

#### Scenario: Domain that is not a bare host refused
- **WHEN** an operator creates an organization with a domain that carries a scheme or a path, such
  as `https://acme.example.com/app`
- **THEN** creation is refused

#### Scenario: An organization cannot exist without a domain
- **WHEN** an operator creates an organization and gives no domain
- **THEN** creation is refused

### Requirement: Keep organization slugs unique
The system SHALL NOT allow two organizations to share a slug, and SHALL compare slugs
case-insensitively. A slug SHALL consist only of lowercase letters, digits and hyphens.

#### Scenario: Duplicate slug refused
- **WHEN** an operator creates an organization whose slug is already taken, differing at most in
  letter case
- **THEN** creation is refused and no second organization exists

#### Scenario: Slug with a disallowed character refused
- **WHEN** an operator creates an organization whose slug contains a character other than a
  lowercase letter, a digit or a hyphen
- **THEN** creation is refused

### Requirement: Create organizations only through an operator command
The system SHALL let an operator create an organization from the command line, and SHALL NOT
expose any public API endpoint that creates, edits or deletes an organization.

#### Scenario: Operator creates an organization
- **WHEN** an operator runs the create-organization command with a name, a slug and a domain
- **THEN** an active organization exists with that name, slug and domain

#### Scenario: No public endpoint creates an organization
- **WHEN** an unauthenticated or authenticated API caller tries to create, edit or delete an
  organization through any API endpoint
- **THEN** no such endpoint exists and no organization changes

### Requirement: Issue a join code once
Every organization SHALL have a join code that a person must present to sign up into it. The
system SHALL show the code to the operator once, when it is created or rotated, and SHALL store
it in a form from which it cannot be recovered.

#### Scenario: Code shown at creation
- **WHEN** an operator creates an organization
- **THEN** the join code is printed once, and no later command or response reveals it again

#### Scenario: Code not recoverable from storage
- **WHEN** the stored join credential of an organization is inspected
- **THEN** it is not equal to the join code and the join code cannot be derived from it by
  reading it

#### Scenario: Rotating replaces the previous code
- **WHEN** an operator rotates an organization's join code
- **THEN** a new code is printed and the previous code no longer allows signup

### Requirement: Every user belongs to exactly one organization
The system SHALL ensure every account created through signup belongs to exactly one organization
from the moment it is created, and SHALL NOT allow any account to belong to two. An account
created outside signup by an operator, such as a superuser, MAY belong to none, and such an
account cannot use the API.

#### Scenario: A new account has an organization
- **WHEN** an account is created through signup
- **THEN** it belongs to the organization named at signup and to no other

#### Scenario: An account cannot be given a second organization
- **WHEN** something attempts to attach an account that already belongs to an organization to a
  second one
- **THEN** the attempt is refused and the account still belongs only to its first organization

#### Scenario: A failed signup leaves nothing behind
- **WHEN** signup fails after the account would have been created but before it was attached to
  its organization
- **THEN** no account exists

### Requirement: Keep email and username unique within an organization only
The system SHALL treat an email address and a username as unique within one organization, so two
different organizations MAY each hold an account with the same email or the same username, and
two accounts in one organization MUST NOT.

#### Scenario: Same email in two organizations
- **WHEN** an email address is registered in one organization and signup is submitted for the same
  address into a different organization
- **THEN** both accounts exist, in their own organizations

#### Scenario: Same username in two organizations
- **WHEN** a username is registered in one organization and signup is submitted for the same
  username into a different organization
- **THEN** both accounts exist, in their own organizations

#### Scenario: Duplicate within one organization
- **WHEN** an email address or a username is already registered in an organization and a second
  signup for it is submitted into that same organization, differing at most in letter case
- **THEN** the second signup is refused and no second account is created

### Requirement: Move existing users into a default organization
When the system is upgraded, every account that existed before it SHALL end up in one
pre-existing default organization, whose domain is the host of the deployment's configured
reset-link base address, and signup into that organization SHALL stay closed until an
operator issues it a join code. No existing account SHALL lose its ability to sign in beyond
the new requirement to name its organization.

#### Scenario: Existing accounts are assigned
- **WHEN** the upgrade is applied to a database that already holds accounts
- **THEN** every one of those accounts belongs to the default organization

#### Scenario: Existing account still signs in
- **WHEN** an account that existed before the upgrade signs in naming the default organization
  with its correct password
- **THEN** signin succeeds

#### Scenario: Default organization is closed to signup until a code is issued
- **WHEN** signup into the default organization is attempted before an operator has issued its
  join code
- **THEN** signup is refused, whatever join code is presented

### Requirement: Let an operator deactivate an organization
The system SHALL let an operator mark an organization inactive, and reactivate it. While an
organization is inactive none of its users can sign in or use an existing token, and nobody can
sign up into it.

#### Scenario: Deactivation takes effect
- **WHEN** an operator marks an organization inactive
- **THEN** signin, signup and every token-authenticated request for that organization are
  refused, and the data of the organization is left intact

#### Scenario: Reactivation restores access
- **WHEN** an operator marks an inactive organization active again
- **THEN** its users can sign in again with their existing credentials
