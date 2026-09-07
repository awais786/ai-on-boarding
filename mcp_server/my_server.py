import asyncio
import os
import re

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.dependencies import get_access_token

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
MAILPIT_BASE_URL = "http://localhost:8025"
RESET_LINK_PATTERN = re.compile(r"/reset-password/([^/\s]+)/")

# Token from the most recent successful `signin`. Caching it here (rather than
# handing it back to the caller) means callers never see the raw token, and
# get_users/password_reset simply forward whatever's cached - Django's own
# IsAdminUser check is what actually enforces "admin only", not this file.
_token = None

@mcp.tool
def greet(name):
    return f"Hello {name}!"

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
async def signin(email_or_username, password):
    """Sign in and cache the token for subsequent get_users/password_reset calls."""
    global _token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{DJANGO_BASE_URL}/api/signin/",
            json={"email_or_username": email_or_username, "password": password},
        )
    if response.status_code == 401:
        return {"status": "failed", "detail": "Unable to sign in with the provided credentials."}
    response.raise_for_status()
    _token = response.json()["token"]
    return {"status": "success"}

@mcp.tool
async def google_signin():
    """Exchange the caller's Google-authenticated MCP session for a Django token.

    Caches the token for subsequent get_users/password_reset/update_password calls, exactly
    like `signin` does - the raw Google access token and the returned Django token are never
    included in this tool's response.
    """
    global _token
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
    response.raise_for_status()
    _token = response.json()["token"]
    return {"status": "success"}

def _auth_headers():
    return {"Authorization": f"Token {_token}"}

@mcp.tool
async def get_users(cursor=None, country=None):
    """List users. Pass `cursor` (from a previous response's `next`/`previous`) to fetch that page.

    Pass `country` to instead walk every page and return every user whose `country` matches
    (case-insensitively) in one flat list - `cursor` is ignored in that mode, since a full walk
    is required to find every match regardless of where it starts.

    Requires a prior `signin` as a staff/admin account.
    """
    if _token is None:
        return {"status": "error", "detail": "Sign in first."}
    async with httpx.AsyncClient() as client:
        if country is not None:
            matches = []
            page_cursor = None
            while True:
                params = {"cursor": page_cursor} if page_cursor else None
                response = await client.get(
                    f"{DJANGO_BASE_URL}/api/users/", headers=_auth_headers(), params=params
                )
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
            f"{DJANGO_BASE_URL}/api/users/", headers=_auth_headers(), params=params
        )
        if response.status_code == 403:
            return {"status": "error", "detail": "Signed-in account is not staff."}
        response.raise_for_status()
        return response.json()

async def _user_exists(client, email):
    """Page through /api/users/ looking for `email` (case-insensitive)."""
    cursor = None
    while True:
        params = {"cursor": cursor} if cursor else None
        response = await client.get(
            f"{DJANGO_BASE_URL}/api/users/", headers=_auth_headers(), params=params
        )
        response.raise_for_status()
        payload = response.json()
        if any(user["email"].lower() == email.lower() for user in payload["results"]):
            return True
        next_url = payload.get("next")
        if not next_url:
            return False
        cursor = httpx.URL(next_url).params["cursor"]


async def _find_reset_code(client, email):
    """Poll Mailpit for the newest reset email to `email` and pull the code out of it."""
    for _ in range(5):
        search = await client.get(
            f"{MAILPIT_BASE_URL}/api/v1/search", params={"query": f"to:{email}"}
        )
        search.raise_for_status()
        messages = search.json()["messages"]
        if messages:
            newest = max(messages, key=lambda message: message["Created"])
            detail = await client.get(f"{MAILPIT_BASE_URL}/api/v1/message/{newest['ID']}")
            detail.raise_for_status()
            match = RESET_LINK_PATTERN.search(detail.json()["Text"])
            if match:
                return match.group(1)
        await asyncio.sleep(0.5)
    return None

@mcp.tool
async def password_reset(email, new_password):
    """Request a password reset for `email` and complete it with the code Mailpit received.

    Requires a prior `signin` as a staff/admin account (used to check the address exists).
    Local-testing automation only: assumes Django is reachable at localhost:8000
    and reset emails land in a Mailpit instance at localhost:8025.
    """
    if _token is None:
        return {"status": "error", "detail": "Sign in first."}
    async with httpx.AsyncClient() as client:
        if not await _user_exists(client, email):
            return {"status": "skipped", "detail": "No account exists for that email."}

        request_response = await client.post(
            f"{DJANGO_BASE_URL}/api/password-reset/", json={"email": email}
        )
        request_response.raise_for_status()

        code = await _find_reset_code(client, email)
        if code is None:
            return {"status": "failed", "detail": "No reset email found in Mailpit."}

        confirm_response = await client.post(
            f"{DJANGO_BASE_URL}/api/password-reset/confirm/",
            json={"code": code, "password": new_password},
        )
        if confirm_response.status_code != 200:
            return {"status": "failed", "detail": confirm_response.json().get("detail")}
        return {"status": "success"}


@mcp.tool
async def update_password(username, new_password, current_password=None):
    """Update the account at `username`'s password via PATCH /api/users/<username>/update-password/.

    Pass `current_password` when `username` is the signed-in caller's own account - the API
    requires it to confirm identity and rejects the request without it. Omit it when the
    signed-in caller is staff updating a *different* account's password; a non-staff caller
    doing the same is rejected.

    Requires a prior `signin`. A non-staff caller may only target their own username;
    a staff/admin caller may target any username.
    """
    if _token is None:
        return {"status": "error", "detail": "Sign in first."}
    update_payload = {"new_password": new_password}
    if current_password is not None:
        update_payload["current_password"] = current_password
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{DJANGO_BASE_URL}/api/users/{username}/update-password/",
            headers=_auth_headers(),
            json=update_payload,
        )
    if response.status_code == 403:
        return {"status": "error", "detail": "You may only update your own password."}
    if response.status_code in (400, 404):
        return {"status": "failed", "detail": response.json()}
    response.raise_for_status()
    return {"status": "success", **response.json()}


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8080)
