# Quickstart: Validate User Signin

## Prerequisites

- Signup is implemented (`specs/001-user-signup/`) and `sdd_django_demo/.venv/bin/python manage.py migrate` has been run, including this feature's `SigninAttempt` migration.
- At least one account exists — create one via the signup endpoint first (see `specs/001-user-signup/quickstart.md`).

## Run the server

```bash
cd sdd_django_demo
.venv/bin/python manage.py runserver
```

## Scenario 1 — successful signin (FR-005, FR-009)

```bash
curl -i -X POST http://127.0.0.1:8000/api/signin/ \
  -H "Content-Type: application/json" \
  -d '{"email": "ada@example.com", "password": "lovelace1"}'
```

Expected: `HTTP/1.1 200 OK`, body `{"token": "<some hex string>"}`.

## Scenario 2 — wrong password (FR-007, FR-008, FR-010)

```bash
curl -i -X POST http://127.0.0.1:8000/api/signin/ \
  -H "Content-Type: application/json" \
  -d '{"email": "ada@example.com", "password": "wrong-password"}'
```

Expected: `HTTP 401`, body `{"detail": "Invalid credentials."}`.

## Scenario 3 — unregistered email (FR-006, FR-008)

```bash
curl -i -X POST http://127.0.0.1:8000/api/signin/ \
  -H "Content-Type: application/json" \
  -d '{"email": "nobody@example.com", "password": "whatever123"}'
```

Expected: identical response to Scenario 2 — same status, same body. Diff the two responses to
confirm.

## Scenario 4 — lockout after 3 failures (FR-012, FR-013)

Repeat Scenario 2's request twice more (3 failures total against `ada@example.com` within 5
minutes), then attempt Scenario 1's *correct* credentials immediately after.

Expected: the third failure and the subsequent correct-credentials attempt both return the same
401 as Scenario 2 — the account is locked even though the password was right the fourth time.

## Scenario 5 — lockout resets (FR-014)

Wait 30 minutes (or, in a test, travel time forward past the lockout window), then repeat
Scenario 1.

Expected: `HTTP 200` with a token — lockout has expired and the correct credentials succeed.

## Scenario 6 — password never returned (FR-011)

Inspect every response body from Scenarios 1–5. None should contain the string `password` or any
submitted password value.

## Scenario 7 — schema and docs

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/schema/
```

Expected: `200`. Open `http://127.0.0.1:8000/api/docs/` and confirm the signin endpoint is listed
— see [contracts/signin.md](./contracts/signin.md) for the documented shape.

## Automated equivalent

Once `api/test_signin.py` exists (written after implementation, from the specification — see
`tasks.md`):

```bash
.venv/bin/pytest -v
```

Expected: all tests pass, including `test_health.py` and `test_signup.py`.
