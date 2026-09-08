"""Every write tool, grouped by domain."""

import backend_client  # module-qualified: signup/request_password_reset/confirm_password_reset
                        # are test seams (see tests/conftest.py)
import session  # module-qualified: get_access_token is a test seam (see tests/conftest.py)
from backend_client import AuthedBackendClient, validate_password_strength


def load_tools(mcp):
    mcp.tool()(signup)
    mcp.tool()(request_password_reset)
    mcp.tool()(reset_password)
    mcp.tool()(change_my_password)
    mcp.tool()(change_user_password)


# --- Account: signup, password reset, changing your own password ------------


async def signup(email: str, username: str, country: str):
    """Create an account. The password is collected on a page this server
    hosts, not a tool argument - never seen by your MCP client or this
    assistant. The backend token for the new account rides inside your signed
    session token, so it can't be granted retroactively - reconnect (or wait
    for your session token to refresh) before other tools recognise it.
    """

    async def _do_signup(values):
        validate_password_strength(values['password'])
        return await backend_client.signup(email, username, values['password'], country)

    return await session._await_secret([('password', 'Password')], 'Choose a password.', _do_signup)


async def request_password_reset(email: str):
    """Request a password-reset code by email. The reply is the same whether or not that
    address has an account - it never reveals who is signed up."""
    return await backend_client.request_password_reset(email)


async def reset_password(code: str):
    """Complete a password reset using the code emailed by request_password_reset.

    The new password is collected on a page this server hosts, not a tool
    argument - never seen by your MCP client or this assistant.
    """

    async def _do_reset(values):
        validate_password_strength(values['new_password'])
        return await backend_client.confirm_password_reset(code, values['new_password'])

    return await session._await_secret([('new_password', 'New password')], 'Choose a new password.', _do_reset)


async def change_my_password():
    """Change your own password. Requires an account - use signup first if you don't have one.

    Both passwords are collected on a page this server hosts, not tool
    arguments - never seen by your MCP client or this assistant.
    """
    session._require_backend_token()
    access_token = session.get_access_token()

    async def _do_change(values):
        validate_password_strength(values['new_password'])
        return await session._call_backend(
            AuthedBackendClient.change_own_password,
            values['current_password'],
            values['new_password'],
            access_token=access_token,
        )

    return await session._await_secret(
        [('current_password', 'Current password'), ('new_password', 'New password')],
        'Enter your current password and choose a new one.',
        _do_change,
    )


# --- Users: managing other users' accounts (admin only) ---------------------


async def change_user_password(username: str):
    """Change a user's password. Only works if the caller is an admin.

    The new password is collected on a page this server hosts, not a tool
    argument - never seen by your MCP client or this assistant.
    """
    session._require_backend_token()
    access_token = session.get_access_token()

    async def _do_change(values):
        validate_password_strength(values['new_password'])
        return await session._call_backend(
            AuthedBackendClient.change_password,
            username,
            values['new_password'],
            access_token=access_token,
        )

    return await session._await_secret(
        [('new_password', "New password")],
        f"Choose {username}'s new password.",
        _do_change,
    )
