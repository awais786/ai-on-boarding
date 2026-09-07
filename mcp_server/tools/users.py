"""Admin tools: listing and managing other users' accounts."""

import django_client
import session


def load_tools(mcp):
    mcp.tool()(list_signup_users)
    mcp.tool()(list_users_by_country)
    mcp.tool()(change_user_password)


async def list_signup_users():
    """List every signed-up user (username, country, signup date). Admin only."""
    session._require_django_token()
    return await session._call_django(django_client.AuthedDjangoClient.list_users)


async def list_users_by_country(country: str):
    """List signed-up users from a specific country. Admin only."""
    session._require_django_token()
    return await session._call_django(django_client.AuthedDjangoClient.list_users, country=country)


async def change_user_password(username: str):
    """Change a user's password. Only works if the caller is an admin.

    The new password is collected on a page this server hosts, not a tool
    argument - never seen by your MCP client or this assistant.
    """
    session._require_django_token()
    access_token = session.get_access_token()

    async def _do_change(values):
        django_client.validate_password_strength(values['new_password'])
        return await session._call_django(
            django_client.AuthedDjangoClient.change_password,
            username,
            values['new_password'],
            access_token=access_token,
        )

    return await session._await_secret(
        [('new_password', "New password")],
        f"Choose {username}'s new password.",
        _do_change,
    )
