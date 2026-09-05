# Traceability: List Users API

One row per requirement in
[`specs/user-listing/spec.md`](./specs/user-listing/spec.md). Code and test paths are relative
to `sdd_django_demo/`.

| Requirement | Code | Test |
|---|---|---|
| Require staff authentication | `api/views.py:UserListView` (`authentication_classes = [TokenAuthentication, SessionAuthentication]`, `permission_classes = [IsAdminUser]`) | `test_list_users_rejects_unauthenticated_request`, `test_list_users_rejects_authenticated_non_staff`, `test_list_users_accepts_staff_request`, `test_list_users_accepts_staff_session_login` |
| Return minimal user fields | `api/serializers.py:UserListSerializer` (`fields = ['id', 'email', 'date_joined', 'country']`) | `test_list_users_response_contains_only_expected_fields` |
| Paginate the user list | `api/views.py:UserListPagination` (`CursorPagination`, `ordering = 'id'`, `page_size = 20`) | `test_list_users_paginates_large_user_set`, `test_list_users_empty_set_returns_success` |
| Include the signup country per account | `api/serializers.py:UserListSerializer.get_country` (reads the reverse one-to-one to `embargo.AccountCountry`, `''` if absent) + `api/views.py:UserListView.queryset` (`select_related('accountcountry')`) | `test_list_users_entry_includes_recorded_country`, `test_list_users_entry_with_no_recorded_country_is_empty` |
| List reflects all signed-up accounts | `api/views.py:UserListView.queryset` (`User.objects.order_by('id')`) + `UserListPagination` (cursor, not offset) | `test_list_users_reflects_newly_signed_up_account_across_all_pages` |

## Notes

- The staff-authentication requirement's tests were verified to actually fail: temporarily
  clearing `permission_classes` on `UserListView` turned
  `test_list_users_rejects_unauthenticated_request` and
  `test_list_users_rejects_authenticated_non_staff` red (both got HTTP 200 instead of the
  expected 401/403), then the permission class was restored.
- Round 1 `/code-review` flagged `PageNumberPagination` as a blocking finding: its numeric-offset
  paging can skip or duplicate rows across pages if a user is inserted or deleted mid-walk,
  violating "List reflects all signed-up accounts" (`... exactly once in the combined results`).
  Fixed by switching to `CursorPagination` ordered by `id` (see `design.md` - Decisions), which
  anchors each page to the last row returned instead of a position. `UserListView.queryset` also
  explicitly orders by `id`, since cursor pagination requires a well-defined ordering.
- Post-review, manual testing surfaced that `UserListView` declaring
  `authentication_classes = [TokenAuthentication]` alone silently dropped DRF's project-wide
  `SessionAuthentication` default for this view only, so a Django admin session login could not
  reach the endpoint even though `design.md` said session auth should stay available. Fixed by
  listing `SessionAuthentication` explicitly alongside `TokenAuthentication`; covered by
  `test_list_users_accepts_staff_session_login`.
- Adding "Include the signup country per account" surfaced that "Return minimal user fields" still
  said the response contains *only* `id`, `email`, `date_joined` - now contradicted by the new
  `country` field. Corrected that requirement's text and scenario in `specs/user-listing/spec.md`
  to include `country` in the allowed field set, and updated
  `test_list_users_response_contains_only_expected_fields` to expect it.
- `UserListSerializer.country` was first implemented as `CharField(source='accountcountry.country',
  default='')`. DRF's attribute-traversal helper returns `None` (not the field's `default`) when a
  reverse one-to-one is missing, so an account with no recorded country serialized `country` as
  `None`, not `''` - `test_list_users_entry_with_no_recorded_country_is_empty` caught this.
  Switched to a `SerializerMethodField` using `getattr(obj, 'accountcountry', None)`, which handles
  the missing-relation case directly; `design.md` - Decisions updated to match.
- Verified `test_list_users_entry_includes_recorded_country` can actually fail: temporarily made
  `get_country` always return `''`, saw the assertion fail (`'' == 'wonderland'`), then restored
  the correct implementation.
- `/code-review` on the country-field diff found no blocking findings (all tests pass, the
  `select_related`/`getattr` pairing is correct, no other caller depends on the old 3-field
  shape). One nit: `get_country` lacked a return type hint, causing a drf-spectacular schema-
  generation warning; fixed (`-> str`) since it was a one-line change.
- Every row has at least one test; every test in `api/test_user_listing.py` serves at least one
  row above. No orphans in either direction.
