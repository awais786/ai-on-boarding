import os

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.sessions import UserSession

mcp = FastMCP(
    "Practice-MCP-Server",
    auth=GoogleProvider(
        client_id=os.environ["GOOGLE_MCP_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_MCP_CLIENT_SECRET"],
        base_url=os.environ.get("GOOGLE_MCP_BASE_URL", "http://127.0.0.1:8080"),
        required_scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
    ),
)

DJANGO_BASE_URL = "http://localhost:8000"
TOKEN_STATE_KEY = "django_token"


async def _get_token(session: UserSession):
    """The Django token from the most recent successful `signin` by this caller.

    Stored in FastMCP's per-user session state (keyed by the caller's authenticated
    Google principal, via `UserSession`) rather than a module-level global or the
    connection-scoped `ctx.session_id`: a global is shared by every concurrent caller
    of this process, so one caller's signin could silently overwrite another's and
    leak one identity's session into another's requests; `ctx.session_id` isn't
    reliable either, since this server's connections are served over the modern
    MCP protocol, which is stateless by construction - every request gets a fresh
    connection with no stable session id, so state keyed on it never survives to the
    next call. Keying on the authenticated principal instead keeps each caller's
    token isolated *and* persistent across calls. Caching it here (rather than
    handing it back to the caller) also means callers never see the raw token -
    get_users simply forwards whatever's cached, and Django's own IsAdminUser check
    is what actually enforces "admin only", not this file.
    """
    return await session.get(TOKEN_STATE_KEY)


async def _set_token(session: UserSession, token):
    await session.set(TOKEN_STATE_KEY, token)

@mcp.tool
async def signup(email, username, password, country):
    """Create an account and return its (normalised) email and username.

    On rejection (bad format, weak password, duplicate email/username, or an
    embargoed country) returns the field-keyed validation errors from the API.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{DJANGO_BASE_URL}/api/signup/",
            json={
                "email": email,
                "username": username,
                "password": password,
                "country": country,
            },
        )
    if response.status_code == 400:
        return {"status": "failed", "detail": response.json()}
    response.raise_for_status()
    return {"status": "success", **response.json()}

@mcp.tool
async def signin(email_or_username, password, session: UserSession):
    """Sign in and cache the token (scoped to this caller) for subsequent get_users calls."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{DJANGO_BASE_URL}/api/signin/",
            json={"email_or_username": email_or_username, "password": password},
        )
    if response.status_code == 401:
        return {"status": "failed", "detail": "Unable to sign in with the provided credentials."}
    response.raise_for_status()
    await _set_token(session, response.json()["token"])
    return {"status": "success"}

@mcp.tool
async def google_signin(session: UserSession):
    """Exchange the caller's Google-authenticated MCP session for a Django token.

    Caches the token for subsequent get_users/update_password calls, exactly like `signin`
    does - the raw Google access token and the returned Django token are never included in
    this tool's response.
    """
    google_token = get_access_token()
    if google_token is None:
        return {"status": "error", "detail": "No authenticated Google session."}
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{DJANGO_BASE_URL}/api/auth/google/",
            json={"access_token": google_token.token},
        )
    if response.status_code == 401:
        return {"status": "failed", "detail": "Unable to authenticate with the provided Google session."}
    if response.status_code == 400:
        return {"status": "failed", "detail": response.json()}
    response.raise_for_status()
    await _set_token(session, response.json()["token"])
    return {"status": "success"}

async def _auth_headers(session: UserSession):
    return {"Authorization": f"Token {await _get_token(session)}"}

@mcp.tool
async def get_users(session: UserSession, cursor=None, country=None):
    """List users. Pass `cursor` (from a previous response's `next`/`previous`) to fetch that page.

    Pass `country` to instead walk every page and return every user whose `country` matches
    (case-insensitively) in one flat list - `cursor` is ignored in that mode, since a full walk
    is required to find every match regardless of where it starts.

    Requires a prior `signin` as a staff/admin account.
    """
    if await _get_token(session) is None:
        return {"status": "error", "detail": "Sign in first."}
    headers = await _auth_headers(session)
    async with httpx.AsyncClient() as client:
        if country is not None:
            matches = []
            page_cursor = None
            while True:
                params = {"cursor": page_cursor} if page_cursor else None
                response = await client.get(
                    f"{DJANGO_BASE_URL}/api/users/", headers=headers, params=params
                )
                if response.status_code == 401:
                    return {"status": "error", "detail": "Authentication token is invalid or expired. Sign in again."}
                if response.status_code == 403:
                    return {"status": "error", "detail": "Signed-in account is not staff."}
                response.raise_for_status()
                payload = response.json()
                matches.extend(
                    user for user in payload["results"]
                    if user["country"].lower() == country.lower()
                )
                next_url = payload.get("next")
                if not next_url:
                    break
                page_cursor = httpx.URL(next_url).params["cursor"]
            return {"status": "success", "country": country, "count": len(matches), "results": matches}

        params = {"cursor": cursor} if cursor else None
        response = await client.get(
            f"{DJANGO_BASE_URL}/api/users/", headers=headers, params=params
        )
        if response.status_code == 401:
            return {"status": "error", "detail": "Authentication token is invalid or expired. Sign in again."}
        if response.status_code == 403:
            return {"status": "error", "detail": "Signed-in account is not staff."}
        response.raise_for_status()
        return response.json()

@mcp.tool
async def update_password(username, new_password, session: UserSession, current_password=None):
    """Update the account at `username`'s password via PATCH /api/users/<username>/update-password/.

    Pass `current_password` when `username` is the signed-in caller's own account - the API
    requires it to confirm identity and rejects the request without it. Omit it when the
    signed-in caller is staff updating a *different* account's password; a non-staff caller
    doing the same is rejected.

    Requires a prior `signin`. A non-staff caller may only target their own username;
    a staff/admin caller may target any username.
    """
    if await _get_token(session) is None:
        return {"status": "error", "detail": "Sign in first."}
    update_payload = {"new_password": new_password}
    if current_password is not None:
        update_payload["current_password"] = current_password
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{DJANGO_BASE_URL}/api/users/{username}/update-password/",
            headers=await _auth_headers(session),
            json=update_payload,
        )
    if response.status_code == 401:
        return {"status": "error", "detail": "Authentication token is invalid or expired. Sign in again."}
    if response.status_code == 403:
        return {"status": "error", "detail": "You may only update your own password."}
    if response.status_code in (400, 404):
        return {"status": "failed", "detail": response.json()}
    response.raise_for_status()
    return {"status": "success", **response.json()}


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8080)
