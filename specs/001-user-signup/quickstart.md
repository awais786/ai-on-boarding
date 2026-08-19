# Quickstart: Validate User Signup

## Prerequisites

- The scaffold at `sdd_django_demo/` is set up (`.venv/` created, dependencies installed)
- `sdd_django_demo/.venv/bin/python manage.py migrate` has been run

## Run the server

```bash
cd sdd_django_demo
.venv/bin/python manage.py runserver
```

## Scenario 1 — successful signup (FR-001, FR-007, FR-011)

```bash
curl -i -X POST http://127.0.0.1:8000/api/signup/ \
  -H "Content-Type: application/json" \
  -d '{"email": "Ada@Example.com", "password": "lovelace1"}'
```

Expected: `HTTP/1.1 200 OK`, body `{"email": "ada@example.com"}` — note the email is returned
lowercased (FR-012). See [contracts/signup.md](./contracts/signup.md) for the full contract.

## Scenario 2 — duplicate email is rejected (FR-005, SC-004)

Repeat the exact request above a second time.

Expected: `HTTP 400`, body naming the `email` field as the problem. No second account exists —
confirm via `manage.py shell -c "from django.contrib.auth.models import User; print(User.objects.filter(email='ada@example.com').count())"`, expect `1`.

## Scenario 3 — case-insensitive duplicate (FR-012)

```bash
curl -i -X POST http://127.0.0.1:8000/api/signup/ \
  -H "Content-Type: application/json" \
  -d '{"email": "ADA@EXAMPLE.COM", "password": "lovelace2"}'
```

Expected: `HTTP 400` — rejected as a duplicate of the account created in Scenario 1, despite the
different capitalisation.

## Scenario 4 — weak password is rejected (FR-006)

```bash
curl -i -X POST http://127.0.0.1:8000/api/signup/ \
  -H "Content-Type: application/json" \
  -d '{"email": "grace@example.com", "password": "short"}'
```

Expected: `HTTP 400`, body naming the `password` field.

## Scenario 5 — password is never returned (FR-009, SC-003)

Inspect every response body from Scenarios 1–4 above. None should contain the string `password`
or the submitted password value in any form.

## Scenario 6 — schema and docs still work

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/schema/
```

Expected: `200`. Open `http://127.0.0.1:8000/api/docs/` and confirm the signup endpoint is listed
with a typed request body — see [contracts/signup.md](./contracts/signup.md) for what "typed"
means here.

## Automated equivalent

Once `api/test_signup.py` exists (written after implementation, from the specification — see
`tasks.md`):

```bash
.venv/bin/pytest -v
```

Expected: all tests pass, including `api/test_health.py`.
