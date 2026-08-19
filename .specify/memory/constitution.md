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

### XII. Code review has a bounded contract, and ends in a verdict

A review is not diligence unless it converges. These rules apply to every review — human or
agent — of code against a specification:

- **A finding blocks merge only if it cites one of three things**: a requirement ID (`FR-XXX`),
  a specific named failing test, or a documented convention (this constitution, or a project
  skill). Anything else — a style preference, "I'd have done this differently," a hypothetical
  not grounded in the spec — is a **nit**: recorded, never blocking.
- **Review runs at most two passes on a given piece of work**: an initial pass, and one
  follow-up after fixes are applied. The follow-up checks only what the first pass raised, plus
  anything the fixes broke — it does not go hunting for new material. Still blocked after two
  passes means the specification is wrong or incomplete, not that the code needs a third look;
  fix the spec and re-plan instead of reviewing again.
- **Every review ends with an explicit verdict, stated plainly**: `Ready to merge: yes` or
  `Ready to merge: no`, never a hedge or an open-ended list with no conclusion. A `no` verdict
  must enumerate every blocking finding by its citation. A `yes` verdict is a legitimate,
  expected outcome — finding nothing wrong is not evidence of insufficient effort, and does not
  need to be padded with nits to look thorough.
- **A review that has not reached a verdict is not finished.** Reporting findings without a
  final yes/no is an incomplete review, not a cautious one.

## Governance

This constitution supersedes convenience. Amendments require an explicit version bump and a note
recording what changed and why.

**Version**: 1.2.0 | **Ratified**: 2026-08-19 | **Last Amended**: 2026-08-19

**Amendment history**:
- 1.2.0 (2026-08-19): Added Principle XII — code review is bounded (two passes max, findings
  must cite `FR-`/a failing test/a documented convention to block) and must end in an explicit
  yes/no verdict. Written in response to open-ended AI review loops that never concluded.
- 1.1.0 (2026-08-19): Added Principle XI — tasks live on GitHub issues, not `tasks.md`. Both
  features had accumulated the same task list in two places (the file and the issue) with no
  benefit from the duplication; Principle VII's wording was updated to match ("GitHub issue
  tasks" rather than "tasks").
