---
name: django-conventions
description: Use when adding or changing any endpoint, model, serializer, view or test in this Django REST project — covers the project's layout, migration policy, auth rules and test conventions so generated code matches what is already here.
---

# Django conventions for this project

How this codebase does Django. Follow it rather than inventing a house style.

## Layout

- Project: `sdd_django_demo` · settings at `sdd_django_demo/settings.py`
- Application code: `api/`
- Tests: `api/tests/`, one file per area, named `test_<area>.py`
- URLs: routed from `sdd_django_demo/urls.py` into each app's `urls.py`

## Adding an endpoint

Four pieces, in this order:

1. A serializer for the request and response shape
2. A view — prefer DRF generic or `APIView` classes over function views
3. A URL entry in the app's `urls.py`
4. Tests covering every behaviour the specification requires

Keep views thin. Validation belongs in the serializer, not the view.

## Migrations

Generate them, never hand-write them:

```bash
.venv/bin/python manage.py makemigrations
```

Never edit a generated migration file. If a migration is wrong, change the model and regenerate.
Always commit migrations — a clean clone must be able to run `migrate`.

## Authentication and passwords

- Use Django's built-in auth. Never hand-roll password hashing, token generation, or session
  handling.
- Set passwords through `set_password()` or `create_user()`. Never assign to `user.password`.
- **Never include a password in any response body**, on the success path or in an error.
- Do not add JWT, OAuth or third-party auth unless a specification requires it.

## Tests

- pytest with pytest-django. Run: `.venv/bin/pytest`
- Name tests after the behaviour they protect, not the function they call:
  `test_duplicate_email_is_rejected`, not `test_signup_2`
- Assert the behaviour, not just the status code. A requirement about what is stored needs an
  assertion about what is stored.
- Use `django_db` marks where the database is needed; do not mock the ORM.

## API schema

`drf-spectacular` generates the OpenAPI schema from serializers. If a schema comes out untyped,
the serializer is too thin — fix the serializer rather than annotating around it.

## Requirement identifiers

Requirements in the specification are numbered `R1`, `R2`, and so on, and the numbers are
permanent. New requirements take the next free number. Changed requirements keep theirs. Removed
ones leave a gap.

Never renumber. The traceability table, pull requests and review comments all reference these
identifiers, and renumbering silently repoints every one of them.

## Things not to do here

- No custom user model unless a specification requires one
- No `settings.py` splits, environment variables, or Docker
- No abstraction introduced for a single caller
- No changes to a test in order to make failing code pass
