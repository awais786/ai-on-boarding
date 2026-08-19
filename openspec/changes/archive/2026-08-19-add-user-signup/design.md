## Context

The scaffold already has Django 6.1, DRF, drf-spectacular, and pytest set up, serving only a
health-check endpoint. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Satisfy every requirement in `specs/user-signup/spec.md` with the smallest change to the
  existing scaffold.

**Non-Goals:**
- No custom user model, no new Django app, no new runtime dependency.
- No email verification, invitation, or approval flow.

## Decisions

**Reuse Django's built-in `User`, with no username.** The spec settles that email is the only
identifier. `User.username` is populated internally from the normalised email purely because the
underlying model requires a value there - it is never read, set, or exposed by any request or
response. Alternative considered: a custom user model with `email` as `USERNAME_FIELD` - rejected
as disproportionate for one endpoint's requirements; revisit if a later feature needs email-based
Django admin login.

**Email normalisation happens once, in the serializer's `validate_email`.** Every downstream
consumer (the uniqueness check, `create_user`) sees the already-lowercased value, rather than
each call site normalising independently.

**Validation lives in a serializer (`SignupSerializer`), not the view.** DRF serializers already
produce the field-keyed error responses the spec requires. Password composition
(`validate_password_strength`) is a serializer-level validator, not a Django
`AUTH_PASSWORD_VALIDATORS` entry, because the rule is specific to this endpoint - a global setting
would also constrain `createsuperuser` and the admin site.

**Password exclusion is structural, not incidental.** The response is built from a dedicated
output-only serializer (`AccountSerializer`, `fields = ['email']`) rather than the input
serializer with the password field suppressed - there is no `password` attribute on the object
being serialized for the response, so there is nothing to accidentally reintroduce later.

**Duplicate detection is defence in depth: a pre-check plus a database-level fallback.** The
initial implementation used only `User.objects.filter(email=...).exists()` before creating the
account - a classic check-then-create race. `/code-review` caught it: two concurrent signups for
the same email could both pass the pre-check, and the second would hit an unhandled
`IntegrityError` on the `username` unique constraint, returning a raw 500 instead of the spec's
400. Fix: `create()` wraps `create_user()` in `transaction.atomic()` and catches `IntegrityError`
outside that block (so the atomic block's own savepoint rollback completes before the exception is
converted), re-raising it as the same field-keyed `ValidationError` the pre-check produces. The
pre-check is kept - it gives a faster, unhandled-transaction-free rejection for the common case;
the atomic/`IntegrityError` path only matters under a genuine race.

## Risks / Trade-offs

- [Two sources of truth for "is this email taken"] → the pre-check and the DB constraint agree by
  construction (both key off the normalised, lowercased email; `username` is set to the same
  value as `email`), and the race path is covered by a dedicated regression test.
- [Response returns HTTP 200 rather than the more conventional 201 for a created resource] →
  deliberate product decision, recorded in the spec; not a defect.
