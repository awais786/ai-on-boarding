# Traceability: add-mcp-signup-and-password-tools

## `specs/mcp-session-auth/spec.md`

| Requirement / Scenario | Code | Test |
|---|---|---|
| Admit a caller with no matching account, without a session credential - No matching account | `mcp_server/server.py::CredentialVerifier.verify_token` (catches `NoDjangoAccountError`, admits with no `DJANGO_TOKEN_CLAIM`) | `mcp_server/tests/test_session_auth.py::test_a_caller_with_no_account_here_is_admitted_with_no_credential` |
| Admit a caller with no matching account, without a session credential - Embargoed account | same | `test_an_embargoed_caller_is_admitted_with_no_credential` |
| (supporting) a no-credential session is still cached, not re-exchanged every request | `CredentialVerifier.verify_token` caches even the no-credential case | `test_a_no_credential_session_is_cached_and_not_re_exchanged` |
| Refuse a tool call made without a session credential - A tool requiring a credential is called without one | `server.py::_require_django_token`, called from `list_signup_users`, `list_users_by_country`, `change_user_password`, `change_my_password` | `test_a_tool_requiring_a_credential_refuses_a_credential_less_caller` |
| Refuse a tool call made without a session credential - Signing up establishes a session credential | `server.py::signup` (`_credentials.replace_django_token` on a successful post-signup exchange) | `test_signing_up_grants_a_credential_without_a_new_session`, `test_auth_tools.py::test_signup_grants_a_credential_usable_by_the_next_call` |
| Refuse a tool call made without a session credential - An embargoed caller's signup attempt does not succeed | `django_client.signup` surfaces Django's own duplicate-account refusal unchanged | `test_auth_tools.py::test_signup_rejects_a_duplicate_email` (an embargoed caller retrying signup hits the same duplicate-email/username path as anyone with an existing account) |
| REMOVED: Refuse a caller this project will not sign in | n/a (behavior removed) | previous tests removed/replaced by the two rows above |

## `specs/mcp-auth-tools/spec.md`

| Requirement / Scenario | Code | Test |
|---|---|---|
| Create an account - Successful signup | `django_client.signup`, `server.signup` | `test_auth_tools.py::test_signup_succeeds_for_a_caller_with_no_credential` |
| Create an account - Signup grants a session credential | `server.signup` (exchange + `replace_django_token`) | `test_auth_tools.py::test_signup_grants_a_credential_usable_by_the_next_call` |
| Create an account - Duplicate email or username | `django_client.signup` (non-200 -> `DjangoAPIError`) | `test_django_client.py::test_signup_rejects_a_duplicate_email`, `test_auth_tools.py::test_signup_rejects_a_duplicate_email` |
| Create an account - Weak password | same | `test_auth_tools.py::test_signup_rejects_a_weak_password` |
| Create an account - Blocked country | same | `test_auth_tools.py::test_signup_rejects_a_blocked_country` |
| Create an account - A password is never returned | `django_client.signup` returns only `{'detail': ...}` | `test_django_client.py::test_signup_never_returns_the_password`, `test_auth_tools.py::test_a_signup_failure_never_returns_the_password` |
| Request a password-reset code - Address has/has no an account | `django_client.request_password_reset`, `server.request_password_reset` (returns Django's body unchanged) | `test_auth_tools.py::test_requesting_a_reset_for_a_registered_address`, `test_requesting_a_reset_for_an_unregistered_address_is_identical` |
| Complete a password reset - Valid code / weak password / invalid code | `django_client.confirm_password_reset`, `server.reset_password` | `test_django_client.py::test_confirm_password_reset_succeeds`, `test_confirm_password_reset_rejects_an_invalid_code`; `test_auth_tools.py::test_reset_password_succeeds_with_a_valid_code`, `test_reset_password_rejects_an_invalid_code`, `test_reset_password_rejects_a_weak_new_password` |
| Complete a password reset - A password is never returned | `django_client.confirm_password_reset` returns only `{'detail': ...}` | `test_django_client.py::test_confirm_password_reset_never_returns_the_new_password`, `test_auth_tools.py::test_a_reset_password_result_never_contains_the_new_password` |
| Change the caller's own password - Correct current password | `django_client.change_own_password`, `server.change_my_password` | `test_django_client.py::test_change_own_password_succeeds`, `test_auth_tools.py::test_change_my_password_succeeds` |
| Change the caller's own password - Wrong current password | `django_client.change_own_password` (400 -> `DjangoAPIError`) | `test_django_client.py::test_change_own_password_rejects_a_wrong_current_password`, `test_auth_tools.py::test_change_my_password_rejects_a_wrong_current_password` |
| Change the caller's own password - No session credential | `server.change_my_password` (`_require_django_token`) | `test_auth_tools.py::test_change_my_password_refuses_a_caller_with_no_credential` |
| Change the caller's own password - Neither password is ever returned | `django_client.change_own_password` returns only `{'detail': ...}` | `test_auth_tools.py::test_change_my_password_never_returns_either_password` |
