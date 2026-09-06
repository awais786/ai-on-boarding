"""Tests for mcp_middleware.PasswordStrengthMiddleware.

No test elsewhere in this suite goes through FastMCP's actual on_call_tool dispatch -
every tool test calls the tool function directly, which never runs any middleware.
These tests build a minimal stand-in for what that dispatch hands a middleware
(a context whose `.message` carries the tool name and raw arguments, and a
`call_next` to invoke the next stage), so a weak password reaching the middleware
undetected is something a test would actually catch.
"""

import pytest

import django_client
from mcp_middleware import PasswordStrengthMiddleware


class FakeToolCallMessage:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class FakeContext:
    def __init__(self, name, arguments):
        self.message = FakeToolCallMessage(name, arguments)


@pytest.fixture
def middleware():
    return PasswordStrengthMiddleware()


@pytest.fixture
def call_next():
    """Records whether it ran, and hands back a sentinel so a test can tell a real
    call happened rather than the middleware returning something of its own."""

    calls = []

    async def _call_next(context):
        calls.append(context)
        return 'tool-ran'

    _call_next.calls = calls
    return _call_next


async def test_signup_with_a_weak_password_never_reaches_the_tool(middleware, call_next):
    context = FakeContext('signup', {'email': 'ada@example.com', 'username': 'ada', 'password': 'weak', 'country': 'GB'})

    with pytest.raises(django_client.DjangoAPIError):
        await middleware.on_call_tool(context, call_next)

    assert call_next.calls == []


async def test_signup_with_a_strong_password_reaches_the_tool(middleware, call_next):
    context = FakeContext(
        'signup', {'email': 'ada@example.com', 'username': 'ada', 'password': 'lovelace1', 'country': 'GB'}
    )

    result = await middleware.on_call_tool(context, call_next)

    assert result == 'tool-ran'
    assert call_next.calls == [context]


async def test_reset_password_checks_new_password_not_the_code(middleware, call_next):
    # The reset code is a string too, but it is not a password and must never be
    # judged as one - even a code that happens to look weak must pass through.
    context = FakeContext('reset_password', {'code': 'weak', 'new_password': 'lovelace1'})

    result = await middleware.on_call_tool(context, call_next)

    assert result == 'tool-ran'


async def test_reset_password_rejects_a_weak_new_password(middleware, call_next):
    context = FakeContext('reset_password', {'code': 'a-valid-code', 'new_password': 'weak'})

    with pytest.raises(django_client.DjangoAPIError):
        await middleware.on_call_tool(context, call_next)

    assert call_next.calls == []


async def test_change_my_password_does_not_check_the_current_password(middleware, call_next):
    # 'weak' as the *current* password must never be judged - it only has to match
    # what is already on record, not meet the strength rule.
    context = FakeContext(
        'change_my_password', {'current_password': 'weak', 'new_password': 'lovelace1'}
    )

    result = await middleware.on_call_tool(context, call_next)

    assert result == 'tool-ran'


async def test_change_my_password_rejects_a_weak_new_password(middleware, call_next):
    context = FakeContext(
        'change_my_password', {'current_password': 'lovelace1', 'new_password': 'weak'}
    )

    with pytest.raises(django_client.DjangoAPIError):
        await middleware.on_call_tool(context, call_next)

    assert call_next.calls == []


async def test_change_user_password_rejects_a_weak_new_password(middleware, call_next):
    context = FakeContext('change_user_password', {'username': 'ada', 'new_password': 'weak'})

    with pytest.raises(django_client.DjangoAPIError):
        await middleware.on_call_tool(context, call_next)


async def test_a_tool_with_no_password_field_is_unaffected(middleware, call_next):
    context = FakeContext('list_signup_users', {})

    result = await middleware.on_call_tool(context, call_next)

    assert result == 'tool-ran'


async def test_a_missing_declared_field_does_not_crash(middleware, call_next):
    # signup's schema requires `password`, but nothing stops a malformed call from
    # omitting it - Django would refuse that on its own; this middleware must not
    # raise a KeyError on the way there.
    context = FakeContext('signup', {'email': 'ada@example.com', 'username': 'ada', 'country': 'GB'})

    result = await middleware.on_call_tool(context, call_next)

    assert result == 'tool-ran'
