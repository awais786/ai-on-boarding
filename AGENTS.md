# ai-on-boarding

This repository demonstrates spec-driven development: a Django REST API (signup, signin) built
from written specifications rather than hand-written code, using
[OpenSpec](https://github.com/Fission-AI/OpenSpec). The actual project lives in
`sdd_django_demo/` — see `sdd_django_demo/AGENTS.md` for its specific conventions, and
`sdd_django_demo/README.md` for the concrete process each feature went through.

## Layout

- `sdd_django_demo/` — the Django + DRF project. Source of truth for what's actually built.
- `openspec/specs/<capability>/spec.md` — the current, canonical spec for each shipped
  capability.
- `openspec/changes/<change-name>/` — an active, in-progress change: `proposal.md`,
  `specs/<capability>/spec.md` (delta), `design.md`, `tasks.md`. Archived once implemented.
- `openspec/changes/archive/<date>-<change-name>/` — completed changes, kept as a historical
  record.
- `openspec/config.yaml` — this project's governing conventions. Read before proposing,
  implementing, or reviewing anything.

## Read before implementing or reviewing anything

`openspec/config.yaml`'s `context`, `rules`, and `operations` sections apply to every change.
The review contract, inlined here so it's never missed:

- A finding blocks merge only if it cites a requirement, a specific named failing test, or a
  documented convention (`openspec/config.yaml`, this file, or `CLAUDE.md`). Anything else is a
  nit — recorded, never blocking.
- Review runs at most two passes: an initial pass, and one follow-up after fixes.
- Every review ends with an explicit verdict — `Ready to merge: yes` or `Ready to merge: no` —
  never an open-ended list with no conclusion.
- Only archive a change once review has returned `Ready to merge: yes` and `pytest` passes for
  the whole project.

Other conventions: tests are written after implementation, from the spec, not TDD; generated
code is never hand-patched (fix the instruction and regenerate); requirement identifiers are
permanent.
