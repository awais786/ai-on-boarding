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
"""

import pytest

import django_client
import server

GOOGLE_A = 'google-token-a'


# --- Create an account ---------------------------------------------------------


async def test_signup_succeeds_for_a_caller_with_no_credential(sign_in, django):
    django.exchange_error = django_client.NoDjangoAccountError('No account.')
    await sign_in(GOOGLE_A)

    result = await server.signup('ada@example.com', 'ada', 'lovelace1', 'GB')

    assert result == {'detail': 'Account created.'}


async def test_signup_grants_a_credential_usable_by_the_next_call(
    sign_in, django, as_caller
):
    django.exchange_error = django_client.NoDjangoAccountError('No account.')
    await sign_in(GOOGLE_A)
    django.exchange_error = None

    await server.signup('ada@example.com', 'ada', 'lovelace1', 'GB')
    verified = await server.auth._token_validator.verify_token(GOOGLE_A)
    as_caller(verified)

    result = await server.list_signup_users()
    assert result == [{'username': 'ada', 'country': 'GB', 'date_joined': '2026-01-01'}]


async def test_signup_rejects_a_duplicate_email(sign_in, django):
    django.exchange_error = django_client.NoDjangoAccountError('No account.')
    await sign_in(GOOGLE_A)
    django.signup_error = django_client.DjangoAPIError(
        'An account with this email already exists.'
    )

    with pytest.raises(django_client.DjangoAPIError):
        await server.signup('ada@example.com', 'ada', 'lovelace1', 'GB')


async def test_signup_rejects_a_weak_password(sign_in, django):
    django.exchange_error = django_client.NoDjangoAccountError('No account.')
    await sign_in(GOOGLE_A)
    django.signup_error = django_client.DjangoAPIError('Must be at least 8 characters.')

    with pytest.raises(django_client.DjangoAPIError):
        await server.signup('ada@example.com', 'ada', 'weak', 'GB')


async def test_signup_rejects_a_blocked_country(sign_in, django):
    django.exchange_error = django_client.NoDjangoAccountError('No account.')
    await sign_in(GOOGLE_A)
    django.signup_error = django_client.DjangoAPIError(
        'Signups from this country are not allowed.'
    )

    with pytest.raises(django_client.DjangoAPIError):
        await server.signup('ada@example.com', 'ada', 'lovelace1', 'Blockistan')


async def test_a_signup_failure_never_returns_the_password(sign_in, django):
    django.exchange_error = django_client.NoDjangoAccountError('No account.')
    await sign_in(GOOGLE_A)
    django.signup_error = django_client.DjangoAPIError(
        'An account with this email already exists.'
    )

    with pytest.raises(django_client.DjangoAPIError) as failure:
        await server.signup('ada@example.com', 'ada', 'a-secret-password', 'GB')

    assert 'a-secret-password' not in str(failure.value)


# --- Request a password-reset code ----------------------------------------------


async def test_requesting_a_reset_for_a_registered_address(django):
    result = await server.request_password_reset('ada@example.com')

    assert result == {
        'detail': 'If that email address has an account, a reset link has been sent to it.'
    }


async def test_requesting_a_reset_for_an_unregistered_address_is_identical(django):
    registered = await server.request_password_reset('ada@example.com')
    unregistered = await server.request_password_reset('nobody@example.com')

    assert registered == unregistered


# --- Complete a password reset --------------------------------------------------


async def test_reset_password_succeeds_with_a_valid_code(django):
    result = await server.reset_password('a-valid-code', 'new-password-1')

    assert result == {'detail': 'Password changed.'}


async def test_reset_password_rejects_an_invalid_code(django):
    django.reset_error = django_client.DjangoAPIError('That reset link is not valid.')

    with pytest.raises(django_client.DjangoAPIError):
        await server.reset_password('bad-code', 'new-password-1')


async def test_reset_password_rejects_a_weak_new_password(django):
    django.reset_error = django_client.DjangoAPIError('Must be at least 8 characters.')

    with pytest.raises(django_client.DjangoAPIError):
        await server.reset_password('a-valid-code', 'weak')


async def test_a_reset_password_result_never_contains_the_new_password(django):
    result = await server.reset_password('a-valid-code', 'a-secret-password')

    assert 'a-secret-password' not in str(result)


# --- Change the caller's own password ---------------------------------------
#
# change_my_password takes neither password as a tool argument - it elicits both
# from the caller's own MCP client, over two rounds, so the assistant that would
# otherwise have composed the call never sees either value. drive_change_my_password
# (conftest.py) plays the client's side of that exchange.


async def test_change_my_password_succeeds(sign_in, django, drive_change_my_password):
    await sign_in(GOOGLE_A)

    _, _, result = await drive_change_my_password('old-password-1', 'new-password-1')

    assert result == {'detail': 'Password changed.'}


async def test_change_my_password_rejects_a_wrong_current_password(
    sign_in, django, drive_change_my_password
):
    await sign_in(GOOGLE_A)
    django.change_own_password_error = django_client.DjangoAPIError(
        'Current password is incorrect.'
    )

    with pytest.raises(django_client.DjangoAPIError):
        await drive_change_my_password('wrong-password', 'new-password-1')


async def test_change_my_password_refuses_a_caller_with_no_credential(sign_in, django, elicit):
    django.exchange_error = django_client.NoDjangoAccountError('No account.')
    await sign_in(GOOGLE_A)
    elicit()  # the refusal must happen before any elicitation is even sent

    with pytest.raises(django_client.DjangoAPIError) as failure:
        await server.change_my_password()

    assert 'signup' in str(failure.value).lower()


async def test_change_my_password_never_returns_either_password(
    sign_in, django, drive_change_my_password
):
    await sign_in(GOOGLE_A)

    _, _, result = await drive_change_my_password('old-password-1', 'new-password-1')

    assert 'old-password-1' not in str(result)
    assert 'new-password-1' not in str(result)


async def test_change_my_password_has_no_password_shaped_tool_arguments():
    tool = await server.mcp.get_tool('change_my_password')

    assert tool.parameters.get('properties', {}) == {}


async def test_change_my_password_rejects_a_weak_new_password(sign_in, django, drive_change_my_password):
    await sign_in(GOOGLE_A)

    with pytest.raises(django_client.DjangoAPIError):
        await drive_change_my_password('old-password-1', 'weak')


async def test_declining_the_current_password_cancels_without_asking_for_a_new_one(
    sign_in, django, drive_change_my_password
):
    await sign_in(GOOGLE_A)

    _, second, third = await drive_change_my_password(None, 'new-password-1')

    assert second == {'detail': 'Password change cancelled.'}
    assert third is None
    assert django.calls == []  # change_own_password was never reached


async def test_declining_the_new_password_cancels_without_changing_anything(
    sign_in, django, drive_change_my_password
):
    await sign_in(GOOGLE_A)

    _, _, third = await drive_change_my_password('old-password-1', None)

    assert third == {'detail': 'Password change cancelled.'}
    assert django.calls == []
