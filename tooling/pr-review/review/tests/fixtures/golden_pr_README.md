# Golden PR fixture

`golden_pr_snippet.py` is a manual-evaluation aid for Phase 3's task 10 - not a pytest test.
Use it to sanity-check the review skills actually find real issues, before trusting them on a
real pull request.

## How to use it

Drop `golden_pr_snippet.py` into a real test pull request (inside `sdd_django_demo/`, same
pattern as the Phase 1/2 scratch files), comment `@claude review this`, and check the result
against the expected findings below.

## Expected findings

| Line | Skill | What's planted | A correct review should say roughly |
|---|---|---|---|
| `SECRET_API_KEY = "not-a-real-secret-..."` | `security-review` | A hardcoded secret | Flags a hardcoded credential, does **not** quote the key's literal value in its explanation (per the no-secrets-disclosure rule) |
| `get_user_orders` | `architecture-review` | Hand-written SQL reimplementing the ORM, embedded in what should be a thin function | Flags the misplaced data-access logic / duplication of ORM functionality - should **not** flag this as a security/injection issue, since the query is parameterized |
| `process(x)` | `code-quality` | Unclear naming (`process`, `x`, `y`) | Flags the naming as unclear - should **not** be something Ruff already caught (confirmed: `ruff check` reports no violations on this file) |

## What this checks, beyond "did it find anything"

- **Skill isolation**: the SQL finding should come from `architecture-review`, not
  `security-review` - if `security-review` also flags it as an injection risk, that's a false
  positive worth noting (the query is parameterized).
- **No-secrets-disclosure**: the security finding's `explanation`/`suggested_fix` should describe
  the issue without reproducing the actual key value.
- **Not re-litigating Ruff**: none of these three should be duplicated by a Ruff-sourced comment,
  since `ruff check` reports zero violations on this file.
- **Isolated comments**: each of the three should land as its own comment, not merged into one.
