"""Everything about a caller's own account: creating it, recovering it, and
changing its password. Calls needing no credential (signup,
request_password_reset, confirm_password_reset, exchange_google_token) stay
module functions; change_own_password needs the caller's token, so it's a
method on AccountClient.
"""

from . import base_client  # module-qualified: send_request/_client are test seams (see tests/test_clients.py)
from .base_client import AuthedClient, BackendAPIError

GOOGLE_AUTH_PATH = '/auth/google/'
SIGNUP_PATH = '/signup/'
PASSWORD_RESET_PATH = '/password-reset/'
PASSWORD_RESET_CONFIRM_PATH = '/password-reset/confirm/'
SELF_CHANGE_PASSWORD_PATH = '/users/me/change-password/'


async def exchange_google_token(google_access_token):
    """Trade a verified Google access token for this project's own backend token."""
    response = await base_client.send_request(
        'POST', GOOGLE_AUTH_PATH, json={'access_token': google_access_token}
    )

    if response.status_code == 401:
        raise BackendAPIError(base_client.extract_error_detail(response), stale_credential=True)
    if response.status_code == 403:
        raise BackendAPIError(base_client.extract_error_detail(response), no_account=True)
    if response.status_code != 200:
        raise BackendAPIError(base_client.extract_error_detail(response))

    return response.json()['token']


async def signup(email, username, password, country):
    """Create an account. No credential is sent - a caller with none is exactly who calls this."""
    response = await base_client.send_request(
        'POST',
        SIGNUP_PATH,
        json={'email': email, 'username': username, 'password': password, 'country': country},
    )
    base_client.raise_for_failure(response)
    return {'detail': 'Account created.'}


async def request_password_reset(email):
    """Ask the backend to email a reset code. The response is identical whether or not the
    address has an account - returned as-is, so that stays true here too."""
    response = await base_client.send_request('POST', PASSWORD_RESET_PATH, json={'email': email})
    base_client.raise_for_failure(response)
    return response.json()


async def confirm_password_reset(code, new_password):
    """Spend a reset code and set the new password."""
    response = await base_client.send_request(
        'POST', PASSWORD_RESET_CONFIRM_PATH, json={'code': code, 'password': new_password}
    )
    base_client.raise_for_failure(response)
    return {'detail': 'Password changed.'}


class AccountClient(AuthedClient):
    """Calls that need the caller's own backend token to act on their own account."""

    async def change_own_password(self, current_password, new_password):
        response = await base_client.send_request(
            'POST',
            SELF_CHANGE_PASSWORD_PATH,
            json={'current_password': current_password, 'new_password': new_password},
            headers=self._headers(),
        )
        base_client.raise_for_failure(response)
        return {'detail': 'Password changed.'}
