## Context

See proposal.md - Why. Signin already issues a DRF auth token (`rest_framework.authtoken.Token`)
on success, but nothing in the project currently requires that token on a request - this is the
first authenticated, authorization-gated endpoint. There is no `is_staff`-granting flow yet;
staff status is set via `createsuperuser` or the Django admin, both out of scope here.

## Goals / Non-Goals

**Goals:**
- Let a staff-authenticated caller retrieve the full list of signed-up users, a page at a time.
- Keep the exposed fields minimal (`id`, `email`, `date_joined`).

**Non-Goals:**
- Filtering, searching, or sorting the user list.
- Any endpoint for granting/revoking staff status - that's managed outside the API today.
- Changing how signin issues tokens.

## Decisions

- **Authentication: `rest_framework.authtoken.TokenAuthentication`.** The signin endpoint
  already issues this token; reusing it means no new credential mechanism is introduced.
  Session authentication is left available via DRF's defaults for browsing `/api/docs/`, but the
  token is the intended caller mechanism.
- **Authorization: DRF's built-in `IsAdminUser` permission.** It checks `request.user.is_staff`,
  which matches "staff or superuser" from the spec (`is_staff=True` is implied for superusers).
  No custom permission class is needed.
- **View: `generics.ListAPIView` over `User.objects.all()`.** Matches the existing pattern in
  `api/views.py` (`SignupView` already subclasses a DRF generic view) and gives pagination for
  free via the view's `pagination_class`.
- **Serializer: new `UserListSerializer`** in `api/serializers.py` exposing only `id`, `email`,
  `date_joined`, alongside the existing `AccountSerializer`/`SignupSerializer` (which expose a
  different field set for a different purpose and are not reused here).
- **Pagination: DRF `CursorPagination`, ordered by `id`, page size 20**, set via the view's
  `pagination_class` rather than project-wide `DEFAULT_PAGINATION_CLASS` in `settings.py` - no
  other endpoint in the project returns a list, so a global default isn't justified yet.
  `PageNumberPagination` was tried first but rejected: it identifies a page by numeric offset,
  so a user created or deleted between two page fetches shifts every later offset, letting a row
  reappear on a later page or be skipped entirely - a direct violation of "List reflects all
  signed-up accounts" (each account exactly once across the combined pages). Cursor pagination
  anchors each page to the last row actually returned rather than a position, so it is immune to
  concurrent inserts/deletes at other points in the ordering.

- **`country` via a `SerializerMethodField` reading `accountcountry.country`.** Country lives on
  a separate one-to-one model (`embargo.AccountCountry`), not on `User` itself, and not every
  account is guaranteed to have a row there. A plain `CharField(source='accountcountry.country',
  default='')` was tried first, but DRF's attribute-traversal helper returns `None` - not the
  field's `default` - when the reverse relation is missing, so that approach serialized a missing
  country as `None` rather than `''`. A `SerializerMethodField` using
  `getattr(obj, 'accountcountry', None)` handles the missing-relation case directly. Add
  `select_related('accountcountry')` to the view's queryset to avoid an extra query per row.

## Risks / Trade-offs

- [No existing account has `is_staff=True` outside a manually-created superuser] → acceptable:
  matches the current admin-access model, and `createsuperuser` already exists as the
  provisioning path.
- [`CursorPagination`'s default `cursor` query param could collide with a future filter param of
  the same name] → low risk given no filtering is planned; revisit if filtering is added later.
- [Some existing accounts may have no `AccountCountry` row] → the new requirement explicitly
  covers this: serialize as empty rather than erroring.
