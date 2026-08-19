# Feature Specification: User Signup

**Feature Branch**: `001-user-signup`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "Build a user signup feature for the Django REST API. A user should be able to create an account using an email address and a password."

## Clarifications

### Session 2026-08-19

- Q: What is the minimum password length for signup, and are there any character-composition rules? → A: Minimum 8 characters, plus at least one letter and one digit.
- Q: What does a successful signup response contain, and what HTTP status code does it return? → A: HTTP 200, body contains the account's email only.
- Q: Is the email-uniqueness check case-sensitive or case-insensitive? → A: Case-insensitive. Email addresses are normalised to lowercase before being stored, so `Ada@example.com` and `ada@example.com` can never both be registered.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create an account (Priority: P1)

A person who does not yet have an account provides an email address and a password, and receives
confirmation that their account now exists.

**Why this priority**: Nothing else in the product is reachable without an account. This is the
entry point.

**Independent Test**: Submit a valid email and password to the signup endpoint and confirm an
account exists afterwards that did not exist before.

**Acceptance Scenarios**:

1. **Given** no account exists for the submitted email, **When** a valid email and password are submitted, **Then** exactly one account is created and a success response is returned.
2. **Given** an account already exists with the submitted email, **When** signup is attempted with that email, **Then** the request is rejected and no second account is created.

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
- What happens when the email has leading or trailing whitespace?
- What happens when both fields are absent entirely?
- What happens when the password is submitted but empty?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept a signup submission containing an email address and a password.
- **FR-002**: The system MUST reject a submission in which the email address is absent or empty.
- **FR-003**: The system MUST reject a submission in which the password is absent or empty.
- **FR-004**: The system MUST reject a submission whose email address is not a valid email address.
- **FR-005**: The system MUST reject a submission whose email address is already registered.
- **FR-006**: The system MUST reject a password shorter than 8 characters, or one that does not contain at least one letter and at least one digit.
- **FR-007**: On a valid submission, the system MUST create exactly one account.
- **FR-008**: The system MUST store the password in a form from which the original password cannot be recovered.
- **FR-009**: The system MUST NOT include the password, in any form, in any response.
- **FR-010**: A rejection MUST identify which field was unacceptable.
- **FR-011**: A successful signup MUST return HTTP 200 with a response body containing the created account's email address and nothing else.
- **FR-012**: The system MUST normalise an email address to lowercase before storing or comparing it, so two accounts can never differ only by case.

### Key Entities

- **Account**: represents a person who can sign in. Holds an email address unique across all accounts, and a stored password credential. There is no separate username in this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person with a valid email and password can create an account in a single request.
- **SC-002**: Every rejection names the field responsible, with no rejection returning only a generic failure.
- **SC-003**: No response emitted by the signup feature contains the submitted password.
- **SC-004**: Two accounts can never exist with the same email address.

## Assumptions

- Signup is open to anyone; no invitation or approval step is required.
- No email verification is performed at signup; the address is recorded, not confirmed.
- No session or token is issued by signup itself. Signing in is a separate feature.
- There is no username distinct from the email address.
