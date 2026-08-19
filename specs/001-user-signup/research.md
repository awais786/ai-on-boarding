# Phase 0 Research: User Signup

No `[NEEDS CLARIFICATION]` markers remain in the Technical Context — the scaffold already fixes
language, framework, and testing stack. The decisions below are the ones the specification left
open for the planning stage.

## Decision: identity model — reuse `django.contrib.auth.User`, no custom user model

**Rationale**: The specification's Key Entities section states there is no username distinct from
the email address, and Django's built-in `User` already has a unique `email` field and secure
password storage via `create_user`/`check_password`. A custom user model is a larger, harder-to-
undo change (it must be set before the first migration) than a single endpoint needing an
email-keyed account justifies.

**Alternatives considered**: A custom user model with `email` as `USERNAME_FIELD` — rejected as
disproportionate for one endpoint's requirements; can be revisited if a later feature needs
email-based Django admin login or email-based `authenticate()` without a workaround.

## Decision: password composition rule enforced in the serializer, not `AUTH_PASSWORD_VALIDATORS`

**Rationale**: FR-006 (8 characters minimum, at least one letter and one digit) is a requirement
of the signup endpoint specifically. Django's `AUTH_PASSWORD_VALIDATORS` setting is global — it
would also constrain `createsuperuser` and any future admin-created account, which the
specification says nothing about.

**Alternatives considered**: A custom entry in `AUTH_PASSWORD_VALIDATORS` — rejected because it
reaches beyond what FR-006 asked for.

## Decision: email normalisation to lowercase in `SignupSerializer.validate_email`

**Rationale**: FR-012 requires case-insensitive comparison implemented as storage-time lowercasing
of the email address. Doing the lowercasing in field-level validation means the value is already
normalised by the time the uniqueness check (FR-005) and `create_user` (FR-007) see it — a single
point of normalisation rather than a rule repeated at each call site.

**Alternatives considered**: A case-insensitive database lookup (e.g. `email__iexact`) without
normalising the stored value — rejected because it satisfies the uniqueness check but leaves
stored emails in mixed case, which the specification's wording ("normalised to lowercase before
being stored") rules out directly.

## Decision: response body is an output-only serializer, not the input serializer with `password` excluded

**Rationale**: FR-009 requires the password never appear in any response, in any form. A
dedicated output representation with only an `email` field makes that true by construction —
there is no `password` attribute on the object being serialized for the response, so there is
nothing to accidentally re-include later if the input serializer changes.

**Alternatives considered**: `write_only=True` on the input serializer's password field — this
would also satisfy FR-009 for the success path, but was rejected in favour of a dedicated output
serializer because it keeps the "what a caller can see" contract in one place (the output
serializer) independent of how the input serializer evolves.
