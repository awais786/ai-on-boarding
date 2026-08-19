# ai-on-boarding

This repository demonstrates spec-driven development: a Django REST API (signup, signin) built
from written specifications rather than hand-written code. The actual project lives in
`sdd_django_demo/` — see `sdd_django_demo/CLAUDE.md` for its specific conventions, and
`sdd_django_demo/README.md` for the concrete process each feature went through.

## Layout

- `sdd_django_demo/` — the Django + DRF project. Source of truth for what's actually built.
- `specs/<NNN-feature>/` — spec.md, plan.md, research.md, data-model.md, contracts/,
  quickstart.md, traceability.md per feature.
- `.specify/memory/constitution.md` — this project's governing principles. Read before
  implementing or reviewing anything, in any directory.
- `reference/`, `glossary.md` — supporting material for readers of this repo.
- `facilitator` branch — teaching material (guide, review checklists, conformance suite), kept
  separate from this branch.

## Read before implementing or reviewing anything

`.specify/memory/constitution.md` governs this repository. The principle most relevant to code
review, inlined here so it's never missed — **Principle XII, the review contract**:

- A finding blocks merge only if it cites a requirement ID (`FR-XXX`), a specific named failing
  test, or a documented convention (the constitution, or a project skill). Anything else is a
  nit: recorded, never blocking.
- Review runs at most two passes on a given piece of work: an initial pass, and one follow-up
  after fixes. The follow-up checks only what the first pass raised, plus anything the fixes
  broke — it does not go hunting for new material.
- Every review ends with an explicit verdict: `Ready to merge: yes` or `Ready to merge: no`,
  never an open-ended list with no conclusion. A `no` verdict enumerates every blocking finding
  by its citation. A `yes` verdict is a legitimate outcome, not evidence of insufficient effort.

Other principles worth knowing up front:

- Every behavioural requirement needs an automated test before it's considered satisfied
  (Principle I); security-sensitive behaviour needs tests that assert it directly, not
  incidentally (Principle II).
- Tests are written after implementation, from the specification — not TDD (Principle X).
- Code is generated from instructions (spec, plan, skills); when generated code is wrong, fix
  the instruction and regenerate rather than hand-patching the output (Principle VIII).
- Tasks are tracked on the feature's GitHub issue, not a `tasks.md` file (Principle XI).

The full list, and the reasoning behind each, is in `.specify/memory/constitution.md`.
