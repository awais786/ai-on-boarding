# Contract: POST /api/signin/

## Request

```
POST /api/signin/
Content-Type: application/json

{
  "email": "ada@example.com",
  "password": "lovelace1"
}
```

Both fields required.

## Responses

### 200 OK — authenticated (FR-009)

```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4"
}
```

No other field is present — in particular, `password` never appears (FR-011).

### 400 Bad Request — missing field

```json
{
  "password": ["This field is required."]
}
```

Structural validation only (FR-002, FR-003) — this is distinct from a credential rejection below.

### 401 Unauthorized — rejected (FR-008, FR-010, FR-013)

```json
{
  "detail": "Invalid credentials."
}
```

Returned identically for **all three** of: an unregistered email, a registered email with the
wrong password, and an email currently locked out (FR-012). A caller cannot distinguish any of
the three from the response alone — that is the point (FR-008, FR-013).
