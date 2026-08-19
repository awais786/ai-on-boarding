# Tasks: User Signup

**Input**: Design documents from `/specs/001-user-signup/`

**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: Not included. The specification states that tests are written after implementation,
derived from the specification, and the constitution forbids a test-driven ordering on this
project. No test tasks are generated.

**Organization**: Tasks are grouped by user story.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Already satisfied by the existing scaffold — Django, DRF, drf-spectacular and pytest
are installed and the `api` app exists. No tasks.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Nothing blocks the user stories. The design introduces no new model, relying on
Django's built-in `User`. No tasks.

---

## Phase 3: User Story 1 - Create an account (Priority: P1) 🎯 MVP

**Goal**: A person with valid details can create exactly one account in a single request.

**Independent Test**: Submit a valid username, email and password and confirm an account exists
afterwards that did not exist before.

### Implementation for User Story 1

- [ ] T001 [US1] Create `SignupSerializer` in `api/serializers.py` accepting `username`, `email` and `password`, all required and non-empty
- [ ] T002 [US1] Add email-format validation to `SignupSerializer`
- [ ] T003 [US1] Add a minimum-length validator of 8 characters to the `password` field, with no character-class rules
- [ ] T004 [US1] Add a uniqueness check on `username` in `SignupSerializer`
- [ ] T005 [US1] Add a case-insensitive uniqueness check on `email` in `SignupSerializer`
- [ ] T006 [US1] Implement account creation in `SignupSerializer.create` using Django's `create_user`, so the password is stored through the configured hasher
- [ ] T007 [US1] Create an output representation in `api/serializers.py` that contains no password field
- [ ] T008 [US1] Implement the signup endpoint in `api/views.py`, returning 201 with the output representation on success
- [ ] T009 [US1] Add the signup route to `api/urls.py`

**Checkpoint**: A valid submission creates exactly one account and returns 201 with no password
in the body.

---

## Phase 4: User Story 2 - Be told what went wrong (Priority: P2)

**Goal**: A rejected submission names the field responsible.

**Independent Test**: Submit a request missing each required field in turn and confirm the
response names the offending field.

### Implementation for User Story 2

- [ ] T010 [US2] Confirm the endpoint returns DRF's field-keyed error body on validation failure, so every rejection identifies its field
- [ ] T011 [US2] Add `drf-spectacular` annotations to the signup endpoint documenting both the success and the rejection responses

**Checkpoint**: Every rejection path names a field, and `/api/docs/` shows the endpoint.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [ ] T012 Verify `/api/schema/` and `/api/docs/` still return 200 with signup present

---

## Dependencies & Execution Order

- T001 blocks T002–T007 (all modify the same serializer)
- T006 depends on T001
- T008 depends on T007
- T009 depends on T008
- T010 depends on T008
- User Story 2 depends on User Story 1

### Parallel Opportunities

None within User Story 1 — every task touches `api/serializers.py` or `api/views.py`.

---

## Notes

- [Story] label maps task to a user story, not to a requirement identifier. Mapping tasks to
  `FR-` identifiers is done by hand in the traceability table.
- Tests are written after this task list is complete, from the specification.
