# sdd_django_demo Constitution

## Core Principles

### I. Every behavioural requirement has automated verification

No requirement in a specification is considered satisfied until a test asserts it. A requirement
with no test is unverified behaviour, regardless of whether the code appears to work.

### II. Security-sensitive behaviour has explicit tests

Authentication, authorisation, credential storage and credential exposure each require tests that
assert the secure behaviour directly, not incidentally through a success path.

### III. Follow existing Django and DRF conventions

Generated code matches the layout, validation style and testing conventions already established
in this project rather than inventing a new house style per feature.

### IV. Prefer simple solutions over unnecessary abstractions

No abstraction is introduced for a single caller. The simplest design that satisfies the
specification wins over one that anticipates requirements nobody has written down.

### V. Tests are never modified to make a failing implementation pass

When a test fails, the implementation is wrong until proven otherwise. Changing the assertion to
match the code turns a green suite into a lie.

### VI. Specifications may evolve when requirements change

A specification is not immutable. When a requirement changes, the specification is updated first.

### VII. A change to the specification propagates outward

Any change to the specification must be reflected in the affected plan, GitHub issue tasks, tests
and code before the change is considered complete. The specification is the source of truth;
every other artefact is downstream of it.

### VIII. Code is generated from instructions, never hand-written

When generated code is wrong, fix the instruction that produced it — the specification, the plan,
or a project skill — rather than the code itself. Patching generated code by hand fixes one
symptom and leaves the instruction defective, so the next regeneration reintroduces the fault.

### IX. Recurring technique belongs in a project skill

A convention repeated across sessions belongs in a project skill, not in a prompt typed again
each time.

### X. Tests are written after the implementation exists, derived from the specification

This project does not practise test-driven development. Tests are written from the specification
once the implementation exists, not generated as tasks that precede it.

### XI. Tasks are tracked on GitHub issues, not a local tasks.md

`/speckit-tasks` output is posted directly to the feature's GitHub issue as a checklist, keyed to
the requirement IDs it implements, instead of being written to `specs/<feature>/tasks.md`. A
`tasks.md` file duplicates the issue with nothing a human or `/speckit-implement` gains from
maintaining twice — the issue is the single place a task's status lives, and it is what
`/speckit-implement` reads when generating code for this project.

## Governance

This constitution supersedes convenience. Amendments require an explicit version bump and a note
recording what changed and why.

**Version**: 1.1.0 | **Ratified**: 2026-08-19 | **Last Amended**: 2026-08-19

**Amendment history**:
- 1.1.0 (2026-08-19): Added Principle XI — tasks live on GitHub issues, not `tasks.md`. Both
  features had accumulated the same task list in two places (the file and the issue) with no
  benefit from the duplication; Principle VII's wording was updated to match ("GitHub issue
  tasks" rather than "tasks").
