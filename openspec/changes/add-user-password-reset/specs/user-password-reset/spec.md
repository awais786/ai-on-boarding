## Purpose

Lets a person who has forgotten their password prove control of their email address and choose a
new one, without the reset path itself becoming a way to discover which email addresses have
accounts or to keep using a token stolen before the reset.

## ADDED Requirements

### Requirement: Accept a reset request
The system SHALL accept a password reset request containing an email address.

#### Scenario: Valid request
- **WHEN** a reset is requested with a non-empty email address
- **THEN** the request is accepted

### Requirement: Reject a reset request with no email
The system SHALL reject a password reset request in which the email address is absent or empty.

#### Scenario: Email omitted
- **WHEN** a reset is requested without an email field
- **THEN** the request is rejected and the response names the email field

### Requirement: Answer every reset request identically
A password reset request SHALL return an identical response - same status, same body - whether
or not the submitted email address has an account. A caller MUST NOT be able to distinguish the
two from the response alone.

#### Scenario: Registered and unregistered addresses are indistinguishable
- **WHEN** a reset is requested for a registered email, and separately for an unregistered one
- **THEN** both responses are identical in status and body

#### Scenario: Reset request response shape
- **WHEN** a reset is requested with a well-formed email address
- **THEN** the response is HTTP 200

### Requirement: Deliver a reset code to a registered address
When a reset is requested for a registered email address, the system SHALL deliver a reset code
to that address, carried as a link the recipient can follow to choose a new password.

#### Scenario: Code delivered to the account holder
- **WHEN** a reset is requested for a registered email
- **THEN** a message containing a link that carries a reset code is sent to that email address

### Requirement: Deliver the reset link as an absolute address
The delivered link SHALL be an absolute address including scheme and host, so that it is usable
directly from a mail client without the recipient having to assemble it.

#### Scenario: Link is followable as sent
- **WHEN** a reset link is delivered
- **THEN** the link includes a scheme and a host rather than being a bare path

### Requirement: Deliver nothing to an unregistered address
When a reset is requested for an email address with no account, the system SHALL NOT deliver a
message to that address.

#### Scenario: No mail to a stranger
- **WHEN** a reset is requested for an email that has no account
- **THEN** no message is sent

### Requirement: Leave earlier codes usable when delivery fails
When a reset code cannot be delivered, the system SHALL leave the account as it was, so that a
code delivered earlier and not yet used stays usable. A person MUST NOT lose the link they
already hold because a later request failed to reach them.

#### Scenario: A failed delivery does not retire the code already sent
- **WHEN** a reset is requested for an address that already holds an unused code, and the new
  message cannot be delivered
- **THEN** the code delivered earlier is still usable

#### Scenario: A failed delivery is answered like any other request
- **WHEN** a reset is requested and the message cannot be delivered
- **THEN** the response is identical to that of a request whose message was delivered

### Requirement: Limit how often a reset may be requested for one address
The system SHALL limit how many reset requests it acts on for the same email address within a
period. Beyond that limit it SHALL issue and deliver nothing further for that address until the
period passes.

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

### Requirement: Never return the reset code in a response
The system SHALL NOT include the reset code, or the link carrying it, in the body of any
response to a request that did not already carry that code. The code is obtainable only by
controlling the email address it was sent to. A caller who follows a reset link has supplied the
code already, so a page served at that link may echo it back.

#### Scenario: Code absent from the request response
- **WHEN** a reset is requested for a registered email
- **THEN** the response body contains neither the reset code nor the link carrying it

### Requirement: Serve a page at the delivered link
Following a delivered reset link SHALL return a page from which the recipient can choose a new
password, so that the link is usable by a person and not only by a programmatic client.

#### Scenario: A usable link opens a form
- **WHEN** a link carrying a usable code is followed
- **THEN** the response is HTTP 200 and offers a form for choosing a new password

#### Scenario: Submitting the form completes the reset
- **WHEN** that form is submitted with an acceptable new password
- **THEN** the reset completes and the account authenticates with the new password

#### Scenario: An unusable link says so and offers no form
- **WHEN** a link carrying an unrecognised, expired, used, or superseded code is followed
- **THEN** the page reports that the link cannot be used, in the same words for all four causes,
  and offers no password form

#### Scenario: A weak password keeps the form open
- **WHEN** the form is submitted with a new password the system would reject
- **THEN** the page reports the problem and the account keeps the password it had

### Requirement: Accept a reset completion
The system SHALL accept a reset completion containing a reset code and a new password.

#### Scenario: Valid completion fields present
- **WHEN** a completion is submitted with a non-empty code and a non-empty new password
- **THEN** the submission proceeds to validation of the code

### Requirement: Reject a reset completion with missing fields
The system SHALL reject a reset completion in which the code or the new password is absent or
empty, and the response SHALL name the missing field.

#### Scenario: Code omitted
- **WHEN** a completion is submitted without a code
- **THEN** the request is rejected and the response names the code field

#### Scenario: New password omitted
- **WHEN** a completion is submitted without a new password
- **THEN** the request is rejected and the response names the password field

### Requirement: Complete a reset with a valid code
A reset completion carrying an unexpired, unused code and an acceptable new password SHALL
succeed, and the account SHALL thereafter authenticate with the new password.

#### Scenario: Password is changed
- **WHEN** a completion is submitted with a valid code and an acceptable new password
- **THEN** the request succeeds with HTTP 200 and the account authenticates with the new password

#### Scenario: The old password stops working
- **WHEN** a reset completes successfully
- **THEN** the password the account previously had no longer authenticates it

### Requirement: Hold a new password to the signup strength rules
A new password supplied during a reset SHALL be subject to the same strength rules the system
applies when an account is created.

#### Scenario: Weak new password is rejected
- **WHEN** a completion is submitted with a new password that signup would have rejected
- **THEN** the request is rejected and the response names the password field

#### Scenario: The account keeps its old password after a rejected completion
- **WHEN** a completion is rejected because the new password is too weak
- **THEN** the account still authenticates with the password it had before

### Requirement: Expire a reset code after 30 minutes
A reset code SHALL stop being usable 30 minutes after it was issued.

#### Scenario: Expired code is refused
- **WHEN** a completion is submitted with a code issued more than 30 minutes earlier
- **THEN** the request is rejected and the password is unchanged

#### Scenario: Code inside the window is accepted
- **WHEN** a completion is submitted with a code issued less than 30 minutes earlier
- **THEN** the request succeeds

### Requirement: Retire a reset code once it is used
A reset code SHALL be usable at most once.

#### Scenario: Replay is refused
- **WHEN** a code that has already completed a reset is submitted a second time
- **THEN** the second request is rejected and the password set by the first reset is unchanged

### Requirement: Supersede an earlier unused code
Requesting a reset SHALL invalidate any reset code previously issued to that email address and
not yet used.

#### Scenario: Only the newest code works
- **WHEN** a second reset is requested for an email that already has an unused code
- **THEN** the earlier code is rejected and the newer code succeeds

### Requirement: Reject every bad code identically
A reset completion refused because its code is unrecognised, expired, already used, or
superseded SHALL return an identical response - same status, same body - in all four cases. A
caller MUST NOT be able to distinguish them from the response alone.

#### Scenario: Unrecognised and expired codes are indistinguishable
- **WHEN** a completion is submitted with an unrecognised code, and separately with an expired
  one
- **THEN** both responses are identical in status and body

#### Scenario: Used and superseded codes are indistinguishable
- **WHEN** a completion is submitted with an already-used code, and separately with a superseded
  one
- **THEN** both responses are identical in status and body

### Requirement: Return HTTP 400 when a reset completion is refused
A reset completion refused because of its code SHALL return HTTP 400.

#### Scenario: Refusal status code
- **WHEN** a completion is refused because its code is not usable
- **THEN** the response status is 400

### Requirement: Invalidate existing authentication tokens on reset
A successful reset SHALL invalidate every authentication token the account already holds, so a
token issued before the reset can no longer be used.

#### Scenario: Pre-existing token stops working
- **WHEN** an account holds an authentication token and then completes a password reset
- **THEN** the token the account held beforehand is no longer valid

### Requirement: Never return a password
The system SHALL NOT include a password, in any form, in any response from either reset
endpoint.

#### Scenario: Password absent from every response
- **WHEN** any reset request or completion is made, successful or not
- **THEN** the response body does not contain the submitted password in any form

### Requirement: Store a new password unrecoverably
A password set through a reset SHALL be stored so that it cannot be read back, matching how
signup stores a password at account creation.

#### Scenario: Stored password is not the submitted text
- **WHEN** a reset completes successfully
- **THEN** the stored representation of the password is not the text that was submitted
