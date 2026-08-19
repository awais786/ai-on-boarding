# sdd_django_demo

This project follows spec-driven development. Before implementing or reviewing anything here,
read `.specify/memory/constitution.md` (repo root, one level up) — its principles govern this
project and are not optional guidance.

The one most relevant to code review, inlined here so it is never missed even if that file isn't
separately opened — **Constitution Principle XII, the review contract**:

- A finding blocks merge only if it cites a requirement ID (`FR-XXX`), a specific named failing
  test, or a documented convention (the constitution, or a project skill). Anything else is a
  nit: recorded, never blocking.
- Review runs at most two passes on a given piece of work: an initial pass, and one follow-up
  after fixes. The follow-up checks only what the first pass raised, plus anything the fixes
  broke.
- Every review ends with an explicit verdict: `Ready to merge: yes` or `Ready to merge: no`,
  never an open-ended list with no conclusion. A `no` verdict enumerates every blocking finding
  by its citation.

Other principles worth knowing before touching this code:

- Every behavioural requirement needs an automated test before it's considered satisfied
  (Principle I); security-sensitive behaviour — auth, credential storage, credential exposure —
  needs tests that assert it directly, not incidentally (Principle II).
- Tests are written after implementation, from the specification — not TDD (Principle X).
- Code is generated from instructions (spec, plan, skills); when generated code is wrong, fix
  the instruction and regenerate rather than hand-patching the output (Principle VIII).
- Tasks are tracked on the feature's GitHub issue, not a `tasks.md` file (Principle XI).

Feature specs live in `../specs/<NNN-feature>/` (spec.md, plan.md, research.md, data-model.md,
contracts/, quickstart.md). See `README.md` in this directory for the concrete process each
feature has gone through so far.
