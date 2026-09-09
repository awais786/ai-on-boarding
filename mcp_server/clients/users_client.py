"""Admin operations on other users' accounts: listing signups, changing
someone else's password. Every call here needs the caller's own backend
token and the backend enforces admin-only on its side - this client just
carries the credential, same as account_client's AccountClient.
"""

from . import base_client  # module-qualified: send_request/_client are test seams (see tests/test_clients.py)
from .base_client import AuthedClient

USERS_PATH = '/users/'

USER_FIELDS = ('username', 'country', 'date_joined')  # id/email deliberately excluded - PII the tools don't need


def _admin_change_password_path(username):
    return f'{USERS_PATH}{username}/change-password/'


class UsersClient(AuthedClient):
    async def _get_users(self, country=None, username=None):
        """The raw, unfiltered rows - id included. Internal use only."""
        params = {}
        if country:
            params['country'] = country
        if username:
            params['username'] = username

        response = await base_client.send_request('GET', USERS_PATH, params=params, headers=self._headers())
        base_client.raise_for_failure(response)
        return response.json()

    async def list_users(self, country=None):
        """Signup users, optionally filtered by country. Stripped to USER_FIELDS,
        real username included - masking it is a read-tool concern, not this
        client's (see tools/users.py)."""
        rows = await self._get_users(country=country)
        return [{field: row[field] for field in USER_FIELDS} for row in rows]

    async def change_password(self, username, new_password):
        response = await base_client.send_request(
            'POST',
            _admin_change_password_path(username),
            json={'password': new_password},
            headers=self._headers(),
        )
        base_client.raise_for_failure(response)
        return {'detail': 'Password changed.'}
