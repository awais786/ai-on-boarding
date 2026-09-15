"""Every tool about a caller's own account: signup, password reset, and
changing your own password."""

import auth as backend_calls  # module-qualified: get_access_token is a test seam (see tests/conftest.py)
import clients.account_client as account_client  # module-qualified: exchange_google_token/signup/
                                                   # request_password_reset/confirm_password_reset
                                                   # are test seams (see tests/conftest.py)
import elicitation as wait_for_secret
from clients.account_client import AccountClient
from mcp.types import ToolAnnotations
from validation import validate_password_strength


def load_tools(mcp):
    # readOnlyHint/destructiveHint decide whether Claude can call a tool
    # without asking first - every tool here changes state, so none is
    # read-only. request_password_reset is not destructive either (it only
    # sends an email); the rest create or overwrite a credential.
    mcp.tool(
        title='Create Account',
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )(signup)
    mcp.tool(
        title='Request Password Reset',
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )(request_password_reset)
    mcp.tool(
        title='Reset Password',
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    )(reset_password)
    mcp.tool(
        title='Change My Password',
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    )(change_my_password)


async def signup(email: str, username: str, country: str):
    """Create an account. The password is collected on a page this server
    hosts, not a tool argument - never seen by your MCP client or this
    assistant. The backend token for the new account rides inside your signed
    session token, so it can't be granted retroactively - reconnect (or wait
    for your session token to refresh) before other tools recognise it.
    """

    async def _do_signup(values):
        validate_password_strength(values['password'])
        return await account_client.signup(email, username, values['password'], country)

    return await wait_for_secret.await_secret([('password', 'Password')], 'Choose a password.', _do_signup)


async def request_password_reset(email: str):
    """Request a password-reset code by email. The reply is the same whether or not that
    address has an account - it never reveals who is signed up."""
    return await account_client.request_password_reset(email)


async def reset_password(code: str):
    """Complete a password reset using the code emailed by request_password_reset.

    The new password is collected on a page this server hosts, not a tool
    argument - never seen by your MCP client or this assistant.
    """

    async def _do_reset(values):
        validate_password_strength(values['new_password'])
        return await account_client.confirm_password_reset(code, values['new_password'])

    return await wait_for_secret.await_secret([('new_password', 'New password')], 'Choose a new password.', _do_reset)


async def change_my_password():
    """Change your own password. Requires an account - use signup first if you don't have one.

    Both passwords are collected on a page this server hosts, not tool
    arguments - never seen by your MCP client or this assistant.
    """
    backend_calls.require_backend_token()
    access_token = backend_calls.get_access_token()

    async def _do_change(values):
        validate_password_strength(values['new_password'])
        return await backend_calls.call_backend(
            AccountClient,
            AccountClient.change_own_password,
            values['current_password'],
            values['new_password'],
            access_token=access_token,
        )

    return await wait_for_secret.await_secret(
        [('current_password', 'Current password'), ('new_password', 'New password')],
        'Enter your current password and choose a new one.',
        _do_change,
    )
