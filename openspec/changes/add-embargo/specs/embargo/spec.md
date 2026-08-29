## Purpose

Maintains a configurable list of blocked countries and provides the check that signup and signin
use to enforce it.

## ADDED Requirements

### Requirement: Maintain a configurable list of blocked countries
The system SHALL maintain a list of blocked countries that can be changed over time. A country
absent from the list SHALL be treated as allowed.

#### Scenario: Unlisted country is allowed
- **WHEN** a country has no entry in the blocked list
- **THEN** a check against that country reports it as allowed

#### Scenario: Listed country is blocked
- **WHEN** a country is on the blocked list
- **THEN** a check against that country reports it as blocked

### Requirement: Match a country case-insensitively
The system SHALL compare a submitted country against the blocked list without regard to letter
case.

#### Scenario: Case-insensitive match
- **WHEN** a country on the blocked list is submitted with different capitalisation
- **THEN** the check reports it as blocked

### Requirement: Evaluate checks against the list's current state
The system SHALL evaluate a country check against the blocked list as it stands at the moment of
the check, not a value cached or recorded from an earlier check.

#### Scenario: A later addition takes effect
- **WHEN** a country is added to the blocked list after an earlier check reported it as allowed
- **THEN** a new check against that country reports it as blocked

#### Scenario: A later removal takes effect
- **WHEN** a country is removed from the blocked list after an earlier check reported it as
  blocked
- **THEN** a new check against that country reports it as allowed
