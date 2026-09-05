## Purpose

Lets an administrator retrieve the list of signed-up user accounts through the API, instead of
needing direct database or Django admin UI access.

## ADDED Requirements

### Requirement: Require staff authentication
The system SHALL reject a request to list users unless the caller is authenticated as a Django
staff or superuser account.

#### Scenario: Unauthenticated request rejected
- **WHEN** a request to list users is made without authentication
- **THEN** the request is rejected and no user data is returned

#### Scenario: Authenticated non-staff request rejected
- **WHEN** a request to list users is made by an authenticated account that is not staff or
  superuser
- **THEN** the request is rejected and no user data is returned

#### Scenario: Staff request accepted
- **WHEN** a request to list users is made by an authenticated staff or superuser account
- **THEN** the request proceeds and returns user data

### Requirement: Return minimal user fields
A successful response SHALL include, for each user, only the `id`, `email`, and `date_joined`
fields - no password data or other account internals.

#### Scenario: Response shape
- **WHEN** a staff caller lists users
- **THEN** each entry in the response body contains only `id`, `email`, and `date_joined`

### Requirement: Paginate the user list
The system SHALL return the user list in fixed-size pages rather than as a single unbounded
response, and SHALL provide a way for the caller to retrieve subsequent pages.

#### Scenario: Large user set is paginated
- **WHEN** the number of signed-up users exceeds one page size
- **THEN** a single response contains at most one page of users, and the response indicates how
  to retrieve the next page

#### Scenario: Empty user set
- **WHEN** no users other than the caller exist
- **THEN** the response is a successful empty (or single-entry) page, not an error

### Requirement: List reflects all signed-up accounts
The system SHALL include every account that exists at request time in the overall list, subject
to pagination.

#### Scenario: Newly signed-up account appears
- **WHEN** an account signs up and a staff caller subsequently lists users across all pages
- **THEN** the new account's `id`, `email`, and `date_joined` appear exactly once in the
  combined results
