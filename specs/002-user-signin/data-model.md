# Data Model: User Signin

## Account (existing, no changes)

Backed by Django's built-in `User`, as established by `specs/001-user-signup/data-model.md`.
Signin reads it (via `authenticate()`) but does not modify it.

## SigninAttempt (new)

Tracks lockout state for FR-012–FR-014. One row per email address that has ever failed a signin
attempt — not one row per attempt.

| Field | Type | Rules |
|---|---|---|
| `email` | string, unique, indexed | The normalised (lowercase) email the attempts were made against. Not required to correspond to a real `Account`. |
| `failed_count` | integer, default 0 | Number of consecutive failures within the current 5-minute window. Reset to 0 on a successful signin (FR-014). |
| `last_failed_at` | datetime, nullable | When the most recent failure was recorded. Null if no failure has ever been recorded, or after a reset. |

**Validation / state-transition rules** (enforced in the signin view, not the model):

1. On a signin attempt, look up (or lazily create) the `SigninAttempt` row for the normalised
   email.
2. If `failed_count >= 3` and `now - last_failed_at < 30 minutes`: the email is locked. Reject
   without attempting authentication (FR-012, FR-013). Do not modify the row.
3. Otherwise, attempt authentication:
   - **Success**: set `failed_count = 0`. Do not modify `last_failed_at` (FR-014).
   - **Failure**: if `last_failed_at` is null or more than 5 minutes old, set `failed_count = 1`;
     otherwise increment `failed_count` by 1. Set `last_failed_at = now`.

**Relationships**: none — `SigninAttempt` is keyed by email string, not a foreign key to
`Account`, precisely because it must also track emails with no matching account (FR-012's
protection covers unregistered emails too).
