## 1. Serializer

- [x] 1.1 Create `UserListSerializer` in `sdd_django_demo/api/serializers.py` exposing `id`,
  `email`, `date_joined` (read-only) from `django.contrib.auth.models.User`

## 2. Endpoint

- [x] 2.1 Implement `UserListView` (`generics.ListAPIView`) in `sdd_django_demo/api/views.py`,
  queryset `User.objects.all()`, `serializer_class = UserListSerializer`,
  `authentication_classes = [TokenAuthentication]`, `permission_classes = [IsAdminUser]`
- [x] 2.2 Add `pagination_class` on the view using DRF `PageNumberPagination` with `page_size =
  20`
- [x] 2.3 Add the `users/` route to `sdd_django_demo/api/urls.py`
- [x] 2.4 Add drf-spectacular schema annotations documenting the success (200, paginated list)
  and rejection (401/403) responses

## 3. Tests (after implementation, from the spec)

- [x] 3.1 List every requirement in `specs/user-listing/spec.md` and what a test would need to
  assert, working only from the spec
- [x] 3.2 Write `sdd_django_demo/api/test_user_listing.py` from that list, covering
  unauthenticated rejection, authenticated-non-staff rejection, staff success, response field
  shape, pagination on a large set, and the empty-set case
- [x] 3.3 Run `pytest` and confirm all tests pass

## 4. Traceability and review

- [x] 4.1 Build `traceability.md` mapping every requirement to its code and test
- [x] 4.2 Run `/code-review` and address any blocking findings
- [x] 4.3 Re-run `/code-review` (verify-only) until `Ready to merge: yes`

## 5. GitHub issue

- [ ] 5.1 Confirm with the user before creating/commenting on the GitHub issue for this change,
  then create it via `gh issue create` if one does not already exist, and post the proposal and
  full delta spec via `gh issue comment`
