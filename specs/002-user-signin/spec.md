# Feature Specification: User Signin

**Feature Branch**: `002-user-signin`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "Build a user signin feature for the Django REST API. A registered user should be able to sign in using their email address and password."

## Clarifications

### Session 2026-08-19

- Q: When signin fails, should the response tell the caller whether the email was unregistered or the password was wrong? → A: No. Both cases return an identical response, so a caller cannot tell which one was true — this prevents email-enumeration attacks.
- Q: What does a successful signin return, and what HTTP status code? → A: HTTP 200, body is `{"token": "<opaque token>"}` — an authentication token the client presents on later requests.
- Q: Is signin rate-limited or does an account lock after repeated failed attempts? → A: Yes. After 3 failed attempts against the same email within a 5-minute window, that email is locked out for 30 minutes. A signin attempt during lockout is rejected with the same generic response as a wrong password (FR-008), so lockout itself does not reveal whether the email is registered.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sign in with valid credentials (Priority: P1)

A person who already has an account provides their email and password, and receives confirmation
that they are signed in.

**Why this priority**: An account that cannot subsequently be used to sign in delivers no value.

**Independent Test**: Create an account directly, then submit its correct email and password to
the signin endpoint and confirm a successful result is returned.

**Acceptance Scenarios**:

1. **Given** a registered account, **When** its correct email and password are submitted, **Then** the request succeeds and a result distinguishable from a rejection is returned.
2. **Given** a registered account, **When** the same credentials are submitted a second time, **Then** signin succeeds again.

---

### User Story 2 - Reject invalid credentials (Priority: P2)

A person who submits the wrong password, or an email nobody registered, is turned away.

**Why this priority**: Signin that accepts anything is not signin.

**Independent Test**: Attempt signin with an email that was never registered, then with a
registered email and the wrong password, and confirm both attempts are rejected.

**Acceptance Scenarios**:

1. **Given** no account exists for the submitted email, **When** signin is attempted, **Then** the request is rejected.
2. **Given** a registered account, **When** signin is attempted with the correct email but the wrong password, **Then** the request is rejected.
3. **Given** the two rejections above, **When** their responses are compared, **Then** they are identical in status and body.

---

### Edge Cases

- What happens when the same email is submitted with different capitalisation?
- What happens when the email or password field is absent entirely?
- What happens when the same correct credentials are used to sign in more than once?
- What happens after repeated failed attempts against the same account?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept a signin submission containing an email address and a password.
- **FR-002**: The system MUST reject a signin submission in which the email address is absent or empty.
- **FR-003**: The system MUST reject a signin submission in which the password is absent or empty.
- **FR-004**: The system MUST authenticate a signin submission against the stored credentials for the account matching the submitted email, compared case-insensitively (consistent with signup's email normalisation).
- **FR-005**: A signin submission with a registered email and its correct password MUST succeed.
- **FR-006**: A signin submission with an email that is not registered MUST be rejected.
- **FR-007**: A signin submission with a registered email and an incorrect password MUST be rejected.
- **FR-008**: A rejected signin MUST return an identical response — same status, same body — whether the email was unregistered or the password was wrong, so a caller cannot distinguish the two.
- **FR-009**: A successful signin MUST return HTTP 200 with a response body containing an opaque authentication token, keyed `token`.
- **FR-010**: A rejected signin MUST return HTTP 401.
- **FR-011**: The system MUST NOT include the password, in any form, in any signin response.
- **FR-012**: After 3 failed signin attempts against the same email within a 5-minute window, the system MUST reject further signin attempts against that email for 30 minutes, even if the correct password is supplied during that period.
- **FR-013**: A rejection caused by lockout (FR-012) MUST return the same response as a wrong-password or unregistered-email rejection (FR-008), so lockout does not reveal whether the email is registered.
- **FR-014**: A successful signin MUST reset the failed-attempt count for that email to zero.

### Key Entities

- **Account**: the same entity introduced by the signup specification — an email address unique across all accounts, and a stored password credential. Signin introduces no new entity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person with correct credentials can sign in in a single request.
- **SC-002**: A person with incorrect credentials, in any form, is never signed in.
- **SC-003**: No response emitted by signin contains the submitted password.

## Assumptions

- Email comparison is case-insensitive, consistent with the signup specification.
- Lockout (FR-012–FR-014) tracks failed attempts per email address, not per IP address or per
  device — a distributed attacker spreading attempts across many source addresses is still
  rate-limited by this rule, but a single legitimate user retrying from multiple devices shares
  the same attempt count.
- Lockout state does not persist beyond its 30-minute window; there is no permanent account
  suspension in this iteration.
