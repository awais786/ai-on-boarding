## Context

See proposal.md - Why. The project already has one authenticated-caller pattern to follow
(`UserListView`: `TokenAuthentication` + `SessionAuthentication`, `IsAdminUser` for the
staff-only case) and one password-changing pattern to reuse (`complete_reset` in
`sdd_django_demo/api/views.py`: `set_password` + delete the account's tokens, in one
transaction). This change combines them for an authenticated, non-staff-or-staff caller instead
of an unauthenticated, code-bearing one.

## Goals / Non-Goals

**Goals:**
- One endpoint that serves both "change my own password" and "admin changes someone else's
  password", per the user's confirmed choice of target-in-URL-path over target-in-body.
- Reuse the existing password-strength validator and token-invalidation logic rather than
  duplicating them.

**Non-Goals:**
- Changing the password-reset (forgot-password) flow - untouched, still the only unauthenticated
  path to a new password.
- A "log out my other sessions" control independent of a password change - out of scope; token
  invalidation here is a side effect of a successful update, as it already is for reset.

## Decisions

- **Route: `PATCH /api/users/<username>/update-password/`.** Per the user's revised choice, the
  target account is identified in the URL by username, not numeric id - looked up case-
  insensitively (`username__iexact`), matching `SigninView`'s existing convention, with a 404 if
  no account matches. A resolved target equal to the caller's own account is the self-service
  case; any other resolved target is the admin case and requires the caller to be staff. One
  view, one URL, branching on `target.pk == request.user.pk` - not two separate endpoints -
  because every requirement in the spec ("self needs current password", "staff can target
  others", "non-staff can't target others") is a rule about the *relationship* between caller and
  target, which is naturally one permission check, not naturally two views.

- **`current_password` is required exactly when the resolved target account is the caller's own
  (`target.pk == request.user.pk`), regardless of staff status.** A staff caller changing their
  *own* password still doesn't know a shortcut around
  proving they hold it - the spec's "Self-service update requires the current password"
  requirement is keyed on whose account it is, not on the caller's role. A staff caller changing
  *someone else's* password never supplies that account's current password, matching "An
  admin-issued update does not require the target's current password".

- **Permission check happens before the current-password / new-password fields are validated.**
  A non-staff caller targeting another account is rejected with 403 before the serializer looks
  at the body, so "the response is 403" doesn't depend on what else was or wasn't submitted -
  mirroring how `UserListView` uses `IsAdminUser` as a permission class rather than a check
  inside the view body. Alternative considered: validate the body first, then check permission -
  rejected because it would make the status code depend on incidental field presence in the
  no-permission case, which the spec does not ask for and would be surprising to test.

- **Reuse `complete_reset`'s token-invalidation shape, not `complete_reset` itself.** Both set a
  password and delete the account's tokens inside one `transaction.atomic()` block, for the same
  reason `complete_reset`'s docstring gives: a failure part-way must not leave the password
  changed while an old token stays valid. They are not unified into one shared function because
  `complete_reset` also spends a `PasswordResetCode`, which has no equivalent here - forcing a
  shared signature over that difference would be the kind of premature abstraction the project
  avoids. Both call sites stay four lines each.

- **New password strength: reuse `validate_password_strength` as a field validator on the
  serializer**, exactly as `PasswordResetConfirmSerializer.password` already does. No new
  validation logic.

- **Serializer shape:** one serializer with `current_password` (`required=False`, checked in the
  view against `request.user.id == <id>` since "is it required" depends on context the field
  itself doesn't have) and `new_password` (`required=True`, `write_only`, strength-validated).
  Considered making the view swap between two serializer classes (self vs. admin); rejected as
  more moving parts than the one conditional check needs.

## Risks / Trade-offs

- [A staff caller's own password update looks identical, request-shape-wise, to a normal user's -
  easy to accidentally special-case staff and skip the current-password check] → the "keyed on
  `<id> == request.user.id`, not on role" decision above and its own spec scenario
  ("Current password omitted" / "correct") exist specifically to make this the tested, spelled-out
  behavior rather than an implementation guess.
- [Token invalidation logic now exists in two places (`complete_reset` and this endpoint) instead
  of one] → accepted per the decision above; the duplication is small (delete-tokens-in-a-
  transaction) and the two call sites have different pre-conditions.
