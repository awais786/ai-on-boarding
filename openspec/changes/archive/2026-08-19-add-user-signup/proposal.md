## Why

The application has no way for a person to create an account. Every other feature (signin,
embargo rules) depends on an account existing first, so this is the entry point.

## What Changes

- Add a signup endpoint accepting an email address and a password.
- Reject invalid or duplicate submissions with a field-keyed error identifying what was wrong.
- Store the password unrecoverably; never return it in any response.

## Capabilities

### New Capabilities

- `user-signup`: account creation via email and password - validation, duplicate rejection,
  password storage, and the success/failure response contract.

### Modified Capabilities

(none - this is the first capability in the project)

## Impact

- New endpoint `POST /api/signup/` in `sdd_django_demo/api/`.
- No new Django app or model - reuses `django.contrib.auth.User`.
- No new dependency - built entirely on the existing scaffold (Django, DRF, drf-spectacular).
