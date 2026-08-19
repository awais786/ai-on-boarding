# sdd_django_demo Constitution

**Version**: 1.0.0 | **Ratified**: 2026-08-19 | **Last Amended**: 2026-08-19

## Core Principles

### I. Every behavioural requirement has automated verification

No requirement in a specification is considered satisfied until a test asserts it. A requirement
with no test is unverified behaviour, regardless of whether the code appears to work.

### II. Security-sensitive behaviour has explicit tests

Authentication, authorisation, credential storage and credential exposure each require tests that
assert the secure behaviour directly, not incidentally through a success path.

### III. Tests are never modified to make a failing implementation pass

When a test fails, the implementation is wrong until proven otherwise. Changing the assertion to
match the code turns a green suite into a lie.

### IV. A change to the specification propagates outward

Any change to the specification must be reflected in the plan, the tasks, the tests and the
implementation before the change is considered complete. The specification is the source of
truth; every other artefact is downstream of it.

### V. When generated output is wrong, fix the instruction that produced it

Patching generated code by hand fixes one symptom and leaves the instruction defective, so the
next regeneration reintroduces the fault. Correct the specification, the constitution or the
project skill instead.

## Governance

This constitution supersedes convenience. Amendments require an explicit version bump and a note
recording what changed and why.

**Version**: 1.0.0
