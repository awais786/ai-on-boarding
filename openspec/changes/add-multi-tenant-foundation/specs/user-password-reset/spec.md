## MODIFIED Requirements

### Requirement: Accept a reset request
The system SHALL accept a password reset request containing an organization slug and an email
address.

#### Scenario: Valid request
- **WHEN** a reset is requested with a non-empty organization and a non-empty email address
- **THEN** the request is accepted

### Requirement: Answer every reset request identically
A password reset request SHALL return an identical response - same status, same body - whether
or not the submitted email address has an account in the named organization, and whether or not
the named organization exists or is active. A caller MUST NOT be able to distinguish these cases
from the response alone.

#### Scenario: Registered and unregistered addresses are indistinguishable
- **WHEN** a reset is requested for an email registered in the named organization, and
  separately for an unregistered one
- **THEN** both responses are identical in status and body

#### Scenario: Address registered only in another organization is indistinguishable
- **WHEN** a reset is requested for an email that has an account only in a different
  organization than the one named
- **THEN** the response is identical in status and body to one for an unregistered email

#### Scenario: Unknown or inactive organization is indistinguishable
- **WHEN** a reset is requested naming an organization that does not exist or is inactive
- **THEN** the response is identical in status and body to one for an unregistered email

#### Scenario: Reset request response shape
- **WHEN** a reset is requested with a well-formed email address and the per-address limit has
  not been reached
- **THEN** the response is HTTP 200

### Requirement: Limit how often a reset may be requested for one address
The system SHALL limit how many reset requests it acts on for the same email address within the
same organization within a period. Beyond that limit it SHALL issue and deliver nothing further
for that address in that organization until the period passes. Requests naming a different
organization SHALL NOT count toward the limit. A request refused by the limit SHALL return
HTTP 429 with a fixed body that does not vary between refusals. Neither the body nor the response
headers SHALL carry a countdown or any other detail about when the request was made or when it
may be retried.

#### Scenario: Two refusals are indistinguishable
- **WHEN** two reset requests for one address are refused by the limit at different moments
- **THEN** both responses are identical in status and body, and neither carries a header naming
  a retry time

#### Scenario: Requests beyond the limit are not acted on
- **WHEN** more reset requests are made for one address than the limit allows
- **THEN** no further code is issued and no further message is sent for that address

#### Scenario: A flood cannot leave an address with no usable code
- **WHEN** a reset is requested repeatedly for one address until the limit is reached
- **THEN** the most recently delivered code is still usable

Note: an earlier code is *not* expected to survive - *Supersede an earlier unused code* requires
the opposite. What the limit guarantees is that the superseding stops, so the last code to reach
the account holder stays usable rather than being replaced indefinitely.

#### Scenario: Reaching the limit does not reveal whether an account exists
- **WHEN** the limit is reached for a registered address, and separately for an unregistered one
- **THEN** both responses are identical in status and body

#### Scenario: One organization's flood does not block another's
- **WHEN** the limit has been reached for an email in one organization and a reset is requested
  for the same email in another organization
- **THEN** the second request is acted on

## ADDED Requirements

### Requirement: Reject a reset request with no organization
The system SHALL reject a password reset request in which the organization is absent or empty.

#### Scenario: Organization omitted
- **WHEN** a reset is requested without an organization field
- **THEN** the request is rejected and the response names the organization field

### Requirement: Look the address up only within the named organization
A reset request SHALL be acted on only for an active account whose email matches within the named
active organization. An account in any other organization that shares the address MUST NOT
receive a code, and MUST NOT have any earlier code superseded.

#### Scenario: Shared address resolves to the named organization
- **WHEN** two organizations each hold an account with the same email and a reset is requested
  naming one of them
- **THEN** a code is delivered for that organization's account only, and the other account's
  usable code, if any, is unchanged

#### Scenario: Inactive account receives nothing
- **WHEN** a reset is requested for the email of an inactive account, or of an account whose
  organization is inactive
- **THEN** no code is issued and no message is sent
