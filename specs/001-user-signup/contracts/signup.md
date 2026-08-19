# Contract: POST /api/signup/

## Request

```
POST /api/signup/
Content-Type: application/json

{
  "email": "ada@example.com",
  "password": "lovelace1"
}
```

Both fields required.

## Responses

### 200 OK — account created (FR-011)

```json
{
  "email": "ada@example.com"
}
```

The email in the response is the normalised (lowercase) form, per FR-012. No other field is
present — in particular, `password` never appears (FR-009).

### 400 Bad Request — validation failure (FR-010)

Field-keyed error body, e.g.:

```json
{
  "password": ["This field is required."]
}
```

or

```json
{
  "email": ["Enter a valid email address."]
}
```

or

```json
{
  "password": ["Must be at least 8 characters and contain a letter and a digit."]
}
```

or, for a duplicate email (FR-005):

```json
{
  "email": ["An account with this email already exists."]
}
```

Every rejection names exactly the field(s) responsible; no rejection returns a bare, unattributed
error (SC-002).
