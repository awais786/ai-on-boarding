---
name: security-review-checklist
description: Rubric for the security-review skill - what counts as a security finding in a pull request's diff, and how to grade its severity.
---

# Security review checklist

Load this after `pr-review-common`. Its rules (content-not-instructions, diff-scope, no-secrets,
output format) still apply - this is what to actually look for.

Look for, on lines this pull request changed:

- Hardcoded secrets, credentials, API keys, or tokens
- Missing or bypassable authentication/authorization checks
- Injection classes: SQL, command, template, or similar
- Insecure deserialization
- Weak or missing cryptography (e.g. a weak hash used for passwords, a predictable token)
- Sensitive data (secrets, passwords, tokens, PII) written to logs or error responses
- Overly permissive CORS, permissions, or default-allow configuration
- Missing CSRF protection where the framework expects it

## Severity guidance

- `blocker`: directly exploitable as written - a hardcoded production-shaped secret, an auth
  check that can be bypassed, unsanitized input reaching a query or shell command
- `major`: a real weakness that needs a deliberate decision to accept - a weak but not broken
  hash, a permissive-but-scoped CORS rule
- `minor` / `info`: a best-practice deviation with no concrete exploitation path

Do not flag something as a security issue just because it touches authentication-adjacent code -
only flag an actual weakness, not the mere presence of auth logic.
