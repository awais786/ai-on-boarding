# Traceability: List Users API

One row per requirement in
[`specs/user-listing/spec.md`](./specs/user-listing/spec.md). Code and test paths are relative
to `sdd_django_demo/`.

| Requirement | Code | Test |
|---|---|---|
| Require staff authentication | `api/views.py:UserListView` (`authentication_classes = [TokenAuthentication, SessionAuthentication]`, `permission_classes = [IsAdminUser]`) | `test_list_users_rejects_unauthenticated_request`, `test_list_users_rejects_authenticated_non_staff`, `test_list_users_accepts_staff_request`, `test_list_users_accepts_staff_session_login` |
| Return minimal user fields | `api/serializers.py:UserListSerializer` (`fields = ['id', 'email', 'date_joined']`) | `test_list_users_response_contains_only_expected_fields` |
| Paginate the user list | `api/views.py:UserListPagination` (`CursorPagination`, `ordering = 'id'`, `page_size = 20`) | `test_list_users_paginates_large_user_set`, `test_list_users_empty_set_returns_success` |
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
- Every row has at least one test; every test in `api/test_user_listing.py` serves at least one
  row above. No orphans in either direction.
