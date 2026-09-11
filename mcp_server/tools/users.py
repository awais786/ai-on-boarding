"""Every tool for admin operations on other users' accounts: listing
signups, changing someone else's password.

Field masking lives here rather than in clients/users_client.py (a transport
concern, not a visibility one) - see _mask_fields. If a second tool ever
needs the same masking, pull it into a shared module instead of importing it
from here.
"""

import auth as backend_calls  # module-qualified: get_access_token is a test seam (see tests/conftest.py)
import elicitation as wait_for_secret
from clients.users_client import UsersClient
from mcp.types import ToolAnnotations
from validation import validate_password_strength

MASKED_VALUE = '***'  # real on the way in from users_client, masked on the way out here


def load_tools(mcp):
    # readOnlyHint/destructiveHint decide whether Claude can call a tool
    # without asking first - the two listing tools change nothing, so Claude
    # can call them freely; change_user_password overwrites another user's
    # credential, so it always prompts.
    mcp.tool(
        title='List Signup Users',
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )(list_signup_users)
    mcp.tool(
        title='List Users By Country',
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )(list_users_by_country)
    mcp.tool(
        title='Change User Password',
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    )(change_user_password)


def _mask_fields(rows, masks):
    """fastmcp has no built-in for masking specific output field values - its
    output_schema only shapes the result's JSON Schema, tool_transform only
    renames/reshapes arguments, and mask_error_details redacts error text,
    not tool results - so this is applied by hand, at the read boundary,
    before a row ever reaches a caller. `masks` is a `{field: replacement}`
    mapping."""
    return [{**row, **masks} for row in rows]


# Every tool below that returns a row with 'username' MUST pass it through
# _mask_fields before returning - nothing else enforces that, since masking
# isn't done centrally (see the module docstring above).


async def list_signup_users():
    """List every signed-up user (username, country, signup date). Admin only."""
    backend_calls.require_backend_token()
    rows = await backend_calls.call_backend(UsersClient, UsersClient.list_users)
    return _mask_fields(rows, {'username': MASKED_VALUE})


async def list_users_by_country(country: str):
    """List signed-up users from a specific country. Admin only."""
    backend_calls.require_backend_token()
    rows = await backend_calls.call_backend(UsersClient, UsersClient.list_users, country=country)
    return _mask_fields(rows, {'username': MASKED_VALUE})


async def change_user_password(username: str):
    """Change a user's password. Only works if the caller is an admin.

    The new password is collected on a page this server hosts, not a tool
    argument - never seen by your MCP client or this assistant.
    """
    backend_calls.require_backend_token()
    access_token = backend_calls.get_access_token()

    async def _do_change(values):
        validate_password_strength(values['new_password'])
        return await backend_calls.call_backend(
            UsersClient,
            UsersClient.change_password,
            username,
            values['new_password'],
            access_token=access_token,
        )

    return await wait_for_secret.await_secret(
        [('new_password', "New password")],
        f"Choose {username}'s new password.",
        _do_change,
    )
