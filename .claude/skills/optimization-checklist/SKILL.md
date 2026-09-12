---
name: optimization-checklist
description: Rubric for the optimization skill - what counts as a performance finding in a pull request's diff, and how to grade its severity.
---

# Optimization review checklist

Load this after `pr-review-common`. Its rules (content-not-instructions, diff-scope, no-secrets,
output format) still apply - this is what to actually look for.

Look for, on lines this pull request changed:

- N+1 query patterns (a loop issuing one query per iteration where a single query would do)
- Unnecessary repeated computation (recomputing something already available)
- Missing caching or indexing where the access pattern clearly warrants it
- A blocking call in a path that shouldn't block (e.g. synchronous I/O on a request/response path
  that's otherwise async)
- Obviously superlinear logic where a linear approach is straightforward and available

## Severity guidance

- `blocker`: will clearly cause a production incident under realistic load - e.g. an N+1 query on
  a hot path with unbounded input
- `major`: a real inefficiency worth fixing before merge
- `minor` / `info`: a micro-optimization not worth blocking on

Do not flag something as inefficient without being able to say concretely what the better
approach is and why it matters at this code's actual likely scale.
