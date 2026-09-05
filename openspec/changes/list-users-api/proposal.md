## Why

There is currently no way to see who has signed up other than querying the database directly or
using the Django admin UI as a superuser. An API-facing way to list users is needed for
admin/operational tooling to work against this service programmatically.

## What Changes

- Add a `GET /api/users/` endpoint that returns a paginated list of signed-up users.
- Restrict access to staff/admin accounts only - a caller who is not authenticated as staff
  receives an error response, not user data.
- Each entry in the list exposes only `id`, `email`, and `date_joined` - no password data or
  other account internals.
- Each entry also exposes the account's signup `country` (recorded via the embargo
  country-recording capability), empty if none was recorded.

## Capabilities

### New Capabilities

- `user-listing`: retrieving the list of signed-up user accounts - access control, response
  shape, and pagination.

### Modified Capabilities

(none - this only adds a new capability)

## Impact

- New endpoint `GET /api/users/` in `sdd_django_demo/api/`.
- No new Django app or model - reuses `django.contrib.auth.User`.
- No new dependency - built on the existing scaffold (Django, DRF, drf-spectacular), using DRF's
  built-in pagination and permission classes.
- No new dependency or model - country is already recorded per account; this only surfaces it in
  the response.
