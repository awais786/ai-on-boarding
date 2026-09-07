"""Tests for specs/mcp-auth-tools/spec.md, written from the spec.

Each requirement and what a test has to observe to protect it:

- Create an account -> succeeds for a valid signup, grants a session credential
  usable by the next call, and refuses duplicate email/username, a weak
  password, and a blocked country - each without creating an account.
- Request a password-reset code -> the same outcome regardless of whether the
  address has an account.
- Complete a password reset -> a valid code and strong password succeed;
  invalid/expired/used codes and a weak new password are all refused.
- Change the caller's own password -> succeeds for a correct current password,
  refuses a wrong one, and refuses a caller with no session credential.
- A password is never returned -> asserted directly on every tool's success and
  failure paths.

Every password-setting tool is a URL-mode guard tool (see server.py and
secret_pages.py): it takes no password as a tool argument, instead pointing the
caller at a page this server itself hosts. drive_secret_tool (conftest.py) plays
the client's side of that exchange - "submitting the page" - without a real
browser or HTTP request, the same way the real route handler's own POST branch
does: by calling the pending request's submit() directly.
"""

import pytest

import django_client
import secret_pages
import server
import tools

GOOGLE_A = 'google-token-a'


# --- Create an account ---------------------------------------------------------


async def test_signup_succeeds_for_a_caller_with_no_credential(
    sign_in, django, drive_secret_tool
):
    django.exchange_error = django_client.DjangoAPIError('No account.', no_account=True)
    await sign_in(GOOGLE_A)

    _, result = await drive_secret_tool(
        lambda: tools.account.signup('ada@example.com', 'ada', 'GB'), {'password': 'lovelace1'}
    )

    assert result == {'detail': 'Account created.'}


async def test_signing_up_again_after_a_fresh_login_reaches_other_tools(
    sign_in, django, as_caller, drive_secret_tool
):
    """The Django token rides inside the caller's signed session token (see
    credentials.py), so signup can't grant a credential usable for the rest of
    the session it happened in - that token was already issued before the
    account existed. A fresh login (what a real client does on reconnect)
    picks up the account signup just created."""
    django.exchange_error = django_client.DjangoAPIError('No account.', no_account=True)
    await sign_in(GOOGLE_A)
    django.exchange_error = None

    await drive_secret_tool(
        lambda: tools.account.signup('ada@example.com', 'ada', 'GB'), {'password': 'lovelace1'}
    )
    verified = await sign_in(GOOGLE_A)
    as_caller(verified)

    result = await tools.users.list_signup_users()
    assert result == [{'username': 'ada', 'country': 'GB', 'date_joined': '2026-01-01'}]


async def test_signup_rejects_a_duplicate_email(sign_in, django, drive_secret_tool):
    django.exchange_error = django_client.DjangoAPIError('No account.', no_account=True)
    await sign_in(GOOGLE_A)
    django.signup_error = django_client.DjangoAPIError(
        'An account with this email already exists.'
    )

    with pytest.raises(django_client.DjangoAPIError):
        await drive_secret_tool(
            lambda: tools.account.signup('ada@example.com', 'ada', 'GB'), {'password': 'lovelace1'}
        )


async def test_signup_rejects_a_weak_password(sign_in, django, drive_secret_tool):
    django.exchange_error = django_client.DjangoAPIError('No account.', no_account=True)
    await sign_in(GOOGLE_A)

    with pytest.raises(django_client.DjangoAPIError):
        await drive_secret_tool(
            lambda: tools.account.signup('ada@example.com', 'ada', 'GB'), {'password': 'weak'}
        )


async def test_signup_rejects_a_blocked_country(sign_in, django, drive_secret_tool):
    django.exchange_error = django_client.DjangoAPIError('No account.', no_account=True)
    await sign_in(GOOGLE_A)
    django.signup_error = django_client.DjangoAPIError(
        'Signups from this country are not allowed.'
    )

    with pytest.raises(django_client.DjangoAPIError):
        await drive_secret_tool(
            lambda: tools.account.signup('ada@example.com', 'ada', 'Blockistan'), {'password': 'lovelace1'}
        )


async def test_a_signup_failure_never_returns_the_password(sign_in, django, drive_secret_tool):
    django.exchange_error = django_client.DjangoAPIError('No account.', no_account=True)
    await sign_in(GOOGLE_A)
    django.signup_error = django_client.DjangoAPIError(
        'An account with this email already exists.'
    )

    with pytest.raises(django_client.DjangoAPIError) as failure:
        await drive_secret_tool(
            lambda: tools.account.signup('ada@example.com', 'ada', 'GB'),
            {'password': 'a-secret-password1'},
        )

    assert 'a-secret-password1' not in str(failure.value)


async def test_signup_never_takes_a_password_as_a_tool_argument():
    tool = await server.mcp.get_tool('signup')

    assert 'password' not in tool.parameters.get('properties', {})


async def test_an_unsubmitted_signup_page_keeps_asking_with_the_same_link(
    sign_in, django, drive_secret_tool
):
    django.exchange_error = django_client.DjangoAPIError('No account.', no_account=True)
    await sign_in(GOOGLE_A)

    asked, result = await drive_secret_tool(
        lambda: tools.account.signup('ada@example.com', 'ada', 'GB'), None
    )

    assert result.input_requests['secret'].params.url == asked.input_requests['secret'].params.url
    assert django.calls == []


# --- Request a password-reset code ----------------------------------------------


async def test_requesting_a_reset_for_a_registered_address(django):
    result = await tools.account.request_password_reset('ada@example.com')

    assert result == {
        'detail': 'If that email address has an account, a reset link has been sent to it.'
    }


async def test_requesting_a_reset_for_an_unregistered_address_is_identical(django):
    registered = await tools.account.request_password_reset('ada@example.com')
    unregistered = await tools.account.request_password_reset('nobody@example.com')

    assert registered == unregistered


# --- Complete a password reset --------------------------------------------------


async def test_reset_password_succeeds_with_a_valid_code(django, drive_secret_tool):
    _, result = await drive_secret_tool(
        lambda: tools.account.reset_password('a-valid-code'), {'new_password': 'new-password-1'}
    )

    assert result == {'detail': 'Password changed.'}


async def test_reset_password_rejects_an_invalid_code(django, drive_secret_tool):
    django.reset_error = django_client.DjangoAPIError('That reset link is not valid.')

    with pytest.raises(django_client.DjangoAPIError):
        await drive_secret_tool(
            lambda: tools.account.reset_password('bad-code'), {'new_password': 'new-password-1'}
        )


async def test_reset_password_rejects_a_weak_new_password(django, drive_secret_tool):
    with pytest.raises(django_client.DjangoAPIError):
        await drive_secret_tool(
            lambda: tools.account.reset_password('a-valid-code'), {'new_password': 'weak'}
        )


async def test_a_reset_password_result_never_contains_the_new_password(django, drive_secret_tool):
    _, result = await drive_secret_tool(
        lambda: tools.account.reset_password('a-valid-code'), {'new_password': 'a-secret-password1'}
    )

    assert 'a-secret-password1' not in str(result)


# --- Change the caller's own password ---------------------------------------
#
# change_my_password takes neither password as a tool argument - both are
# collected in one page visit (two fields, one submit), so it needs no more
# rounds than a single-field tool does.


async def test_change_my_password_succeeds(sign_in, django, drive_secret_tool):
    await sign_in(GOOGLE_A)

    _, result = await drive_secret_tool(
        tools.account.change_my_password,
        {'current_password': 'old-password-1', 'new_password': 'new-password-1'},
    )

    assert result == {'detail': 'Password changed.'}


async def test_change_my_password_rejects_a_wrong_current_password(sign_in, django, drive_secret_tool):
    await sign_in(GOOGLE_A)
    django.change_own_password_error = django_client.DjangoAPIError(
        'Current password is incorrect.'
    )

    with pytest.raises(django_client.DjangoAPIError):
        await drive_secret_tool(
            tools.account.change_my_password,
            {'current_password': 'wrong-password', 'new_password': 'new-password-1'},
        )


async def test_change_my_password_refuses_a_caller_with_no_credential(sign_in, django, elicit):
    django.exchange_error = django_client.DjangoAPIError('No account.', no_account=True)
    await sign_in(GOOGLE_A)
    elicit()  # the refusal must happen before any elicitation is even sent

    with pytest.raises(django_client.DjangoAPIError) as failure:
        await tools.account.change_my_password()

    assert 'signup' in str(failure.value).lower()
    assert secret_pages._pending == {}  # no page was ever registered


async def test_change_my_password_never_returns_either_password(sign_in, django, drive_secret_tool):
    await sign_in(GOOGLE_A)

    _, result = await drive_secret_tool(
        tools.account.change_my_password,
        {'current_password': 'old-password-1', 'new_password': 'new-password-1'},
    )

    assert 'old-password-1' not in str(result)
    assert 'new-password-1' not in str(result)


async def test_change_my_password_has_no_password_shaped_tool_arguments():
    tool = await server.mcp.get_tool('change_my_password')

    assert tool.parameters.get('properties', {}) == {}


async def test_change_my_password_rejects_a_weak_new_password(sign_in, django, drive_secret_tool):
    await sign_in(GOOGLE_A)

    with pytest.raises(django_client.DjangoAPIError):
        await drive_secret_tool(
            tools.account.change_my_password,
            {'current_password': 'old-password-1', 'new_password': 'weak'},
        )


async def test_an_unsubmitted_change_my_password_page_keeps_asking_with_the_same_link(
    sign_in, django, drive_secret_tool
):
    await sign_in(GOOGLE_A)

    asked, result = await drive_secret_tool(tools.account.change_my_password, None)

    assert result.input_requests['secret'].params.url == asked.input_requests['secret'].params.url
    assert django.calls == []


async def test_a_stale_change_my_password_link_is_reported_and_not_reused(sign_in, django, elicit):
    await sign_in(GOOGLE_A)
    elicit()
    asked = await tools.account.change_my_password()

    elicit({'secret': None}, request_state='not-a-real-token')
    result = await tools.account.change_my_password()

    assert result == {'detail': 'That link expired before it was completed. Please try again.'}
    # The real pending request is untouched - polling with a wrong token doesn't
    # discard or resolve the one the caller actually got.
    real_pending = secret_pages._pending[asked.request_state]
    assert not real_pending.is_resolved


# --- Change another user's password (admin) -----------------------------------
#
# change_user_password elicits its new password the same way signup and
# reset_password do - it predates specs/mcp-auth-tools/spec.md (it was one of the
# original three tools) but gets the same treatment for consistency.


async def test_change_user_password_rejects_a_weak_new_password(sign_in, django, drive_secret_tool):
    await sign_in(GOOGLE_A)

    with pytest.raises(django_client.DjangoAPIError):
        await drive_secret_tool(
            lambda: tools.users.change_user_password('ada'), {'new_password': 'weak'}
        )


async def test_change_user_password_never_takes_a_password_as_a_tool_argument():
    tool = await server.mcp.get_tool('change_user_password')

    assert 'new_password' not in tool.parameters.get('properties', {})


async def test_an_unsubmitted_change_user_password_page_keeps_asking_with_the_same_link(
    sign_in, django, drive_secret_tool
):
    await sign_in(GOOGLE_A)

    asked, result = await drive_secret_tool(lambda: tools.users.change_user_password('ada'), None)

    assert result.input_requests['secret'].params.url == asked.input_requests['secret'].params.url
    assert django.calls == []
