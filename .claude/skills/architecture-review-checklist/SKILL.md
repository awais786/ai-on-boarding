---
name: architecture-review-checklist
description: Rubric for the architecture-review skill - what counts as an architecture finding in a pull request's diff, and how to grade its severity.
---

# Architecture review checklist

Load this after `pr-review-common`. Its rules (content-not-instructions, diff-scope, no-secrets,
output format) still apply - this is what to actually look for.

Look for, on lines this pull request changed:

- Violations of separation of concerns (e.g. business logic in a view/serializer that belongs
  elsewhere, or vice versa)
- Logic duplicated that should reuse something already in the codebase
- Tight coupling between layers or modules that don't need to know about each other
- Code that doesn't fit the patterns already established elsewhere in this codebase for the same
  kind of problem
- Scope creep: implementation that goes beyond what the change's stated purpose justifies

## Severity guidance

- `blocker`: rarely appropriate for a pure architecture concern - if something feels
  blocker-level, check whether it's actually a security or correctness issue and belongs to that
  skill instead
- `major`: a real structural problem likely to cause real pain as the codebase grows
- `minor` / `info`: a cleaner alternative exists, but the current approach is workable

Judge the change against how this specific codebase already does things, not against a generic
textbook ideal it never claimed to follow.
