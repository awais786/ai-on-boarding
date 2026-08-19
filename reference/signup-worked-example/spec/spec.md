# Feature Specification: User Signup

**Feature Branch**: `feature/signup`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "Build a user signup feature for the Django REST API. A user should be able to create an account using a username, an email address and a password."

## Clarifications

### Session 2026-08-19

- Q: What is the minimum password length, and are there composition rules? → A: Minimum 8 characters. No composition rules — no required mix of character classes.
- Q: Are email addresses compared case-sensitively when checking for duplicates? → A: No. Email addresses are compared case-insensitively, so Ada@example.com and ada@example.com are the same address.
- Q: What status code does a successful signup return? → A: 201 Created.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create an account (Priority: P1)

A person who does not yet have an account provides a username, an email address and a password,
and receives confirmation that their account now exists.

**Why this priority**: Nothing else in the product is reachable without an account. This is the
entry point.

**Independent Test**: Submit a valid username, email and password to the signup endpoint and
confirm an account exists afterwards that did not exist before.

**Acceptance Scenarios**:

1. **Given** no account exists for the submitted username or email, **When** a valid username, email and password are submitted, **Then** exactly one account is created and a success response is returned.
2. **Given** an account already exists with the submitted username, **When** signup is attempted with that username, **Then** the request is rejected and no second account is created.

---

### User Story 2 - Be told what went wrong (Priority: P2)

A person whose submission is rejected is told which field was unacceptable and why, so they can
correct it rather than guess.

**Why this priority**: Signup that fails silently is indistinguishable from a broken service.

**Independent Test**: Submit a request missing each required field in turn and confirm the
response names the offending field.

**Acceptance Scenarios**:

1. **Given** a submission missing the password, **When** signup is attempted, **Then** the response is a client error naming the password field.
2. **Given** a submission with a malformed email address, **When** signup is attempted, **Then** the response is a client error naming the email field.

---

### Edge Cases

- What happens when the same email is submitted with different capitalisation?
- What happens when the username contains leading or trailing whitespace?
- What happens when all three fields are absent entirely?
- What happens when the password is submitted but empty?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept a signup submission containing a username, an email address and a password.
- **FR-002**: The system MUST reject a submission in which the username is absent or empty.
- **FR-003**: The system MUST reject a submission in which the email address is absent or empty.
- **FR-004**: The system MUST reject a submission in which the password is absent or empty.
- **FR-005**: The system MUST reject a submission whose email address is not a valid email address.
- **FR-006**: The system MUST reject a submission whose username is already registered.
- **FR-007**: The system MUST reject a submission whose email address is already registered.
- **FR-008**: The system MUST reject a password shorter than 8 characters. No character-class composition rules apply.
- **FR-009**: On a valid submission the system MUST create exactly one account.
- **FR-010**: The system MUST store the password in a form from which the original password cannot be recovered.
- **FR-011**: The system MUST NOT include the password, in any form, in any response.
- **FR-012**: A rejection MUST identify which field was unacceptable.
- **FR-013**: A successful signup MUST return a response distinguishable from a rejection by status alone.
- **FR-014**: The system MUST compare email addresses case-insensitively when determining whether an address is already registered.
- **FR-015**: A successful signup MUST return HTTP 201.

### Key Entities

- **Account**: represents a person who can sign in. Holds a username unique across all accounts, an email address unique across all accounts, and a stored password credential.

## Success Criteria *(mandatory)*

- **SC-001**: A person with valid details can create an account in a single request.
- **SC-002**: Every rejection names the field responsible, with no rejection returning only a generic failure.
- **SC-003**: No response emitted by the signup feature contains the submitted password.
- **SC-004**: Two accounts can never exist with the same username, or with the same email address.

## Assumptions

- Signup is open to anyone; no invitation or approval step is required.
- No email verification is performed at signup; the address is recorded, not confirmed.
- No session or token is issued by signup itself. Signing in is a separate feature.
- Usernames are compared case-sensitively.
