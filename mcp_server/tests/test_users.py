"""Tests for app/tools/users.py - the admin listing tools.

Username masking lives here, not in clients/users_client.py (see that file's
own docstring): fastmcp has no built-in for masking specific output fields,
only for redacting error text (mask_error_details), so masking is asserted
directly against this tool layer rather than through the client.
"""

import tools
from clients import users_client

GOOGLE_A = 'google-token-a'


async def test_list_signup_users_masks_every_username(sign_in, django, monkeypatch):
    async def _list_users(client, country=None):
        return [
            {'username': 'ada', 'country': 'GB', 'date_joined': '2026-01-01'},
            {'username': 'grace', 'country': 'US', 'date_joined': '2026-01-02'},
        ]

    monkeypatch.setattr(users_client.UsersClient, 'list_users', _list_users)
    await sign_in(GOOGLE_A)

    result = await tools.users.list_signup_users()

    assert [row['username'] for row in result] == ['***', '***']
    assert 'ada' not in str(result)
    assert 'grace' not in str(result)


async def test_list_signup_users_keeps_other_fields_unmasked(sign_in, django):
    await sign_in(GOOGLE_A)

    result = await tools.users.list_signup_users()

    assert result == [{'username': '***', 'country': 'GB', 'date_joined': '2026-01-01'}]


async def test_list_users_by_country_masks_too(sign_in, django):
    await sign_in(GOOGLE_A)

    result = await tools.users.list_users_by_country('GB')

    assert result == [{'username': '***', 'country': 'GB', 'date_joined': '2026-01-01'}]
