# sdd_django_demo

This project follows spec-driven development via OpenSpec. Read `../openspec/config.yaml`
(repo root) before implementing or reviewing anything here — its `context`, `rules`, and
`operations` sections govern this project.

Review contract: a finding blocks merge only if it cites a requirement, a specific named failing
test, or a documented convention (`openspec/config.yaml`, `CLAUDE.md`, or this file) — anything
else is a nit. Review runs at most two passes. Every review ends with an explicit
`Ready to merge: yes`/`no` verdict.

Tests are written after implementation, from the spec, not TDD. Generated code is never
hand-patched — fix the instruction and regenerate. Requirement identifiers in
`openspec/specs/*/spec.md` are permanent.

Feature specs: `../openspec/specs/` (canonical), `../openspec/changes/` (in-progress or
archived). See `README.md` for the process each feature has gone through.
