# Traceability: add-multi-tenant-foundation

Paths are under `sdd_django_demo/api/`. Tests: **ORG** = `test_tenant_organizations.py`,
**ISO** = `test_tenant_isolation.py`, **FLOW** = `test_tenant_auth_flows.py`,
**SU** = `test_signup.py`, **SI** = `test_signin.py`, **PR** = `test_password_reset.py`.
Code: **models** = `models.py`, **ser** = `serializers.py`, **views** = `views.py`,
**mcp** = `mcp_views.py`.

## tenant-organizations

| Requirement | Code | Test |
|---|---|---|
| Describe an organization | models `Organization` | ORG `test_a_new_organization_is_active_and_carries_name_slug_and_timestamps` |
| Give every organization a unique domain | models `Organization.site` (one-to-one to `Site`); `management/commands/create_organization.py` | ORG `test_a_new_organization_is_active_and_carries_name_slug_and_timestamps`, `test_a_domain_already_taken_by_another_organization_is_refused`, `test_the_database_itself_refuses_two_organizations_on_one_site`, `test_a_domain_that_is_not_a_bare_host_is_refused`, `test_an_organization_cannot_be_created_without_a_domain`, `test_an_organization_row_cannot_exist_without_a_site`, `test_the_domain_is_stored_lowercase_and_a_port_is_allowed`, `test_the_upgrade_gives_the_default_organization_the_reset_link_host`, `test_reapplying_after_a_rollback_gives_unlinked_organizations_a_placeholder_domain` |
| Keep organization slugs unique | models `Organization.slug` (unique), `organization_slug_format` check constraint | ORG `test_a_duplicate_slug_is_refused_by_the_database`, `test_a_slug_differing_only_in_case_is_refused`, `test_a_slug_with_a_disallowed_character_is_refused`, `test_the_command_refuses_a_duplicate_or_malformed_slug` |
| Create organizations only through an operator command | `management/commands/create_organization.py`; no route in `urls.py` | ORG `test_no_api_route_creates_edits_or_deletes_an_organization`, `test_the_join_code_is_printed_at_creation_and_opens_signup` |
| Issue a join code once | models `Organization.issue_join_code`, `hash_join_code`; `rotate_join_code.py` | ORG `test_the_stored_join_credential_is_not_the_code`, `test_no_later_command_reveals_the_code_again`, `test_rotating_replaces_the_previous_code`, `test_rotating_an_unknown_organization_is_an_error` |
| Every user belongs to exactly one organization | models `Membership.user` (one-to-one); ser `SignupSerializer.create` (one transaction) | ORG `test_an_account_cannot_be_given_a_second_organization`, `test_a_signup_that_fails_before_attaching_leaves_no_account`, `test_a_signed_up_account_belongs_to_the_organization_named` |
| Keep email and username unique within an organization only | models `Membership` constraints `membership_unique_org_email`, `membership_unique_org_username`; `apps.py` hook removed; `migrations/0007_drop_global_email_unique_index.py` | ORG `test_the_same_email_and_username_can_exist_in_two_organizations`, `test_the_same_email_twice_in_one_organization_is_refused_by_the_database`, `test_the_same_username_twice_in_one_organization_is_refused_by_the_database`; FLOW `test_the_same_email_and_username_can_sign_up_into_two_organizations` |
| Move existing users into a default organization | `migrations/0006_default_organization.py` | ORG `test_existing_accounts_land_in_the_default_organization_and_can_still_sign_in`, `test_the_default_organization_is_closed_to_signup_until_a_code_is_issued`, `test_the_upgrade_refuses_to_guess_between_clashing_accounts`, `test_the_default_organization_starts_with_no_join_code_at_all` |
| Let an operator deactivate an organization | models `Organization.is_active`; `admin.py` `OrganizationAdmin` | ORG `test_deactivating_an_organization_closes_signin_and_signup_and_reactivating_reopens_them` |

## tenant-isolation

| Requirement | Code | Test |
|---|---|---|
| Take the tenant from the credential, never from client input | `tenancy.py::organization_of`; `authentication.py::TenantTokenAuthentication`; `settings.py` `DEFAULT_AUTHENTICATION_CLASSES` | ISO `test_naming_another_organization_in_a_request_changes_nothing`, `test_a_django_admin_session_cannot_reach_tenant_endpoints` |
| Refuse a token whose user is inactive | `TenantTokenAuthentication.authenticate_credentials` | ISO `test_a_token_issued_before_the_user_was_deactivated_stops_working` |
| Refuse a token whose organization is inactive | `TenantTokenAuthentication.authenticate_credentials` | ISO `test_a_token_stops_working_when_its_organization_is_deactivated_and_resumes_on_reactivation`, `test_deactivating_one_organization_does_not_affect_another`, `test_the_refusal_is_the_same_whichever_check_failed` |
| Refuse a token that has no organization | `TenantTokenAuthentication.authenticate_credentials` (`membership is None`) | ISO `test_an_account_outside_every_organization_is_refused` |
| Scope the user list to the caller's organization | `tenancy.py::users_in`; mcp `UserListView.get_queryset` | ISO `test_the_user_list_contains_only_the_admins_own_organization`, `test_a_username_filter_cannot_reach_another_organization`, `test_a_country_filter_cannot_reach_another_organization`, `test_the_same_username_in_two_organizations_lists_only_the_callers` |
| Scope admin password changes to the caller's organization | mcp `AdminChangePasswordView.post` (`users_in`, `membership__username`) | ISO `test_an_admin_changes_the_password_of_a_user_in_their_own_organization`, `test_an_admin_cannot_change_a_password_in_another_organization`, `test_the_same_username_in_two_organizations_changes_only_the_callers` |
| Never reveal another organization through a response | same as above (ordinary 404) | ISO `test_another_organizations_user_and_a_nonexistent_one_look_identical` |
| Refuse a Google sign-in for an inactive organization | `google_auth.py::resolve_google_user` | ISO `test_google_signin_is_refused_for_an_inactive_organization_like_an_unknown_address`, `test_google_signin_is_refused_for_an_inactive_user`, `test_google_signin_is_refused_when_the_address_is_in_two_active_organizations`, `test_a_dormant_duplicate_in_an_inactive_organization_does_not_block_a_live_account` |

## user-signup (modified / added)

| Requirement | Code | Test |
|---|---|---|
| Accept a signup submission (MODIFIED) | ser `SignupSerializer` (`organization`, `join_code`) | SU `test_signup_allows_unblocked_country`, `test_signup_success_returns_200_with_email_and_username` |
| Reject a duplicate email (MODIFIED) | ser `SignupSerializer.validate`, `.create` (IntegrityError branch) | SU `test_signup_rejects_duplicate_email`, `test_signup_duplicate_email_is_case_insensitive`, `test_signup_duplicate_email_race_returns_400_not_500`; FLOW `test_a_duplicate_within_the_organization_is_still_refused`, `test_the_same_email_and_username_can_sign_up_into_two_organizations` |
| Reject a duplicate username (MODIFIED) | same | SU `test_signup_rejects_duplicate_username`, `test_signup_duplicate_username_is_case_insensitive`, `test_signup_duplicate_username_race_returns_400_not_500`; FLOW as above |
| Reject a missing organization | ser `SignupSerializer.organization` | FLOW `test_signup_without_an_organization_names_the_organization_field` |
| Reject a missing join code | ser `SignupSerializer.join_code` | FLOW `test_signup_without_a_join_code_names_the_join_code_field` |
| Admit a signup only with the organization's join code | ser `SignupSerializer.validate`; models `Organization.accepts_join_code` | FLOW `test_signup_with_the_correct_join_code_creates_the_account_in_that_organization`, `test_signup_with_a_wrong_join_code_creates_nothing`, `test_signup_with_another_organizations_join_code_creates_nothing_in_either`, `test_a_caller_cannot_place_themselves_in_an_organization_whose_code_they_lack`, `test_signup_with_a_rotated_away_join_code_is_refused` |
| Refuse an unknown, inactive or wrongly-coded organization identically | ser `SignupSerializer.validate` (`JOIN_REFUSED_MESSAGE`) | FLOW `test_the_four_organization_failures_are_indistinguishable`, `test_a_duplicate_does_not_confirm_that_an_organization_exists` |
| Never return the join code | ser `join_code` is `write_only`; `AccountSerializer` | FLOW `test_the_join_code_is_never_in_a_signup_response` |

## user-signin (modified / added)

| Requirement | Code | Test |
|---|---|---|
| Accept a signin submission (MODIFIED) | ser `SigninSerializer.organization` | SI `test_signin_succeeds_by_email`, `test_signin_succeeds_by_username` |
| Authenticate against the matching account (MODIFIED) | views `SigninView.post` (`Membership` lookup in the organization) | SI `test_signin_email_match_is_case_insensitive`, `test_signin_username_match_is_case_insensitive`; FLOW `test_the_same_email_in_two_organizations_signs_in_to_each_with_its_own_password` |
| Reject all failure modes identically (MODIFIED) | views `SigninView.post` (single `SIGNIN_REJECTION_BODY`) | SI `test_signin_unregistered_email_or_username_and_wrong_password_are_identical`, `test_signin_lockout_matches_wrong_password_response`; FLOW `test_every_failure_mode_matches_a_wrong_password`, `test_a_user_of_one_organization_cannot_sign_in_to_another` |
| Lock an email out after repeated failures (MODIFIED) | views `SigninView.post` (`attempt_key = "<slug>\|<identifier>"`); models `SigninAttempt.email_or_username` | SI `test_signin_locks_out_after_third_failure`, `test_signin_lockout_expires_after_30_minutes`, `test_signin_lockout_applies_regardless_of_email_or_username_form`; FLOW `test_lockout_in_one_organization_does_not_lock_out_the_same_email_in_another`, `test_lockout_of_a_name_that_matches_no_account_is_kept_per_organization` |
| Reject a missing organization | ser `SigninSerializer.organization` | FLOW `test_signin_without_an_organization_names_the_organization_field` |
| Issue a token bound to the account's organization | views `SigninView.post` + `TenantTokenAuthentication` | FLOW `test_a_token_from_signin_acts_only_in_its_own_organization` |

## user-password-reset (modified / added)

| Requirement | Code | Test |
|---|---|---|
| Accept a reset request (MODIFIED) | ser `PasswordResetRequestSerializer.organization` | PR `test_reset_request_with_an_email_is_accepted` |
| Answer every reset request identically (MODIFIED) | views `PasswordResetRequestView.post` | PR (existing identical-response tests); FLOW `test_an_address_registered_only_elsewhere_gets_the_unregistered_response_and_no_mail`, `test_an_unknown_or_inactive_organization_gets_the_unregistered_response` |
| Limit how often a reset may be requested for one address (MODIFIED) | views `PasswordResetAddressThrottle.get_cache_key` | PR (existing limit tests); FLOW `test_one_organizations_flood_does_not_throttle_the_same_address_in_another` |
| Reject a reset request with no organization | ser `PasswordResetRequestSerializer.organization` | FLOW `test_reset_without_an_organization_names_the_organization_field` |
| Deliver the reset link as an absolute address (MODIFIED) | views `build_reset_link` (host from `organization.site.domain`); `migrations/0008_organization_site.py` | FLOW `test_the_reset_link_points_at_the_accounts_organization_domain`, `test_two_organizations_get_links_with_their_own_hosts`, `test_a_forged_host_header_does_not_change_the_link_host`, `test_the_link_keeps_the_scheme_and_path_prefix_from_the_configured_base`; PR `test_the_delivered_link_is_absolute`, `test_the_link_host_comes_from_the_setting_not_the_request` |
| Look the address up only within the named organization | views `PasswordResetRequestView.post` (`Membership` in the organization, `user.is_active`) | FLOW `test_a_shared_address_is_reset_only_in_the_named_organization`, `test_an_inactive_account_receives_no_reset_code` |
