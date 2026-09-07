"""Self-service account tools: signup, password reset, and changing your own password."""

import django_client
import session


def load_tools(mcp):
    mcp.tool()(signup)
    mcp.tool()(request_password_reset)
    mcp.tool()(reset_password)
    mcp.tool()(change_my_password)


async def signup(email: str, username: str, country: str):
    """Create an account. The password is collected on a page this server
    hosts, not a tool argument - never seen by your MCP client or this
    assistant. The Django token for the new account rides inside your signed
    session token, so it can't be granted retroactively - reconnect (or wait
    for your session token to refresh) before other tools recognise it.
    """

    async def _do_signup(values):
        django_client.validate_password_strength(values['password'])
        return await django_client.signup(email, username, values['password'], country)

    return await session._await_secret([('password', 'Password')], 'Choose a password.', _do_signup)


async def request_password_reset(email: str):
    """Request a password-reset code by email. The reply is the same whether or not that
    address has an account - it never reveals who is signed up."""
    return await django_client.request_password_reset(email)


async def reset_password(code: str):
    """Complete a password reset using the code emailed by request_password_reset.

    The new password is collected on a page this server hosts, not a tool
    argument - never seen by your MCP client or this assistant.
    """

    async def _do_reset(values):
        django_client.validate_password_strength(values['new_password'])
        return await django_client.confirm_password_reset(code, values['new_password'])

    return await session._await_secret([('new_password', 'New password')], 'Choose a new password.', _do_reset)


async def change_my_password():
    """Change your own password. Requires an account - use signup first if you don't have one.

    Both passwords are collected on a page this server hosts, not tool
    arguments - never seen by your MCP client or this assistant.
    """
    session._require_django_token()
    access_token = session.get_access_token()

    async def _do_change(values):
        django_client.validate_password_strength(values['new_password'])
        return await session._call_django(
            django_client.AuthedDjangoClient.change_own_password,
            values['current_password'],
            values['new_password'],
            access_token=access_token,
        )

    return await session._await_secret(
        [('current_password', 'Current password'), ('new_password', 'New password')],
        'Enter your current password and choose a new one.',
        _do_change,
    )
