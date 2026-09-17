---
name: code-quality-checklist
description: Rubric for the code-quality skill - what counts as a code-quality finding in a pull request's diff, explicitly excluding anything Ruff already checks, and how to grade its severity.
---

# Code quality review checklist

Load this after `pr-review-common`. Its rules (content-not-instructions, diff-scope, no-secrets,
output format) still apply - this is what to actually look for.

Ruff already runs on every pull request and catches syntax-level style, unused imports, import
ordering, and other mechanical lint issues. Do not re-check any of that - if you find yourself
about to flag something Ruff would already catch, leave it out. Your job is the judgment calls a
deterministic linter cannot make.

Look for, on lines this pull request changed:

- Naming that's misleading or unclear about what a variable, function, or class actually does
- Dead code: something added but never used, or made unreachable
- Logic that is *confusing* rather than *wrong* - hard to follow, not why it does what it does
- Missing tests for security-sensitive behaviour specifically (authentication, credential
  handling, credential exposure) - this repository's own convention requires a direct test for
  such behaviour, not just incidental coverage through a success-path test

## Severity guidance

- `blocker`: essentially never appropriate for a pure code-quality concern - if something feels
  blocker-level, it's probably actually a security or architecture finding and that skill should
  flag it instead
- `major`: reserve for something that will actively mislead the next person to touch this code
- `minor` / `info`: most genuine code-quality findings belong at this level

Be sparing. A bot that flags everything gets ignored; flag only what a careful human reviewer
would actually bring up.
