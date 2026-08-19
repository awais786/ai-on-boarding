# Data Model: User Signup

## Account

Represents a person who can sign in. Backed by Django's built-in `django.contrib.auth.User` —
no new model or migration is introduced by this feature.

| Field | Type | Rules |
|---|---|---|
| `email` | string | Required. Must be a valid email address (FR-004). Normalised to lowercase before storage and comparison (FR-012). Unique across all accounts (FR-005). |
| `password` | string, write-only | Required. At least 8 characters, containing at least one letter and at least one digit (FR-006). Stored through Django's configured password hasher (FR-008); never present in any response (FR-009). |
| `username` (internal) | string | Not part of this feature's contract. Populated from the normalised email at creation time solely because `User.username` is required by the underlying model; no request or response field exposes it. |

**Validation rules** (enforced in `SignupSerializer`, in this order):

1. `email` present and non-empty (FR-002)
2. `email` is a syntactically valid address (FR-004)
3. `password` present and non-empty (FR-003)
4. `password` is at least 8 characters and contains a letter and a digit (FR-006)
5. `email`, normalised to lowercase, is not already registered (FR-005, FR-012)

**State transitions**: none. An account, once created, is not modified or deleted by this
feature.

**Relationships**: none — signup introduces no relationship to any other entity.
