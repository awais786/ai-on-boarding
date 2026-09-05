import asyncio
import os
import re

import httpx
from fastmcp import FastMCP

mcp = FastMCP("Practice-MCP-Server")

DJANGO_BASE_URL = "http://localhost:8000"
MAILPIT_BASE_URL = "http://localhost:8025"
RESET_LINK_PATTERN = re.compile(r"/reset-password/([^/\s]+)/")

@mcp.tool
def greet(name):
    return f"Hello {name}!"

@mcp.tool
async def get_users(cursor=None):
    """List users. Pass `cursor` (from a previous response's `next`/`previous`) to fetch that page."""
    token = os.environ["MCP_API_TOKEN"]
    headers = {"Authorization": f"Token {token}"}
    params = {"cursor": cursor} if cursor else None
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DJANGO_BASE_URL}/api/users/", headers=headers, params=params
        )
        response.raise_for_status()
        return response.json()

async def _user_exists(client, email):
    """Page through /api/users/ looking for `email` (case-insensitive)."""
    token = os.environ["MCP_API_TOKEN"]
    headers = {"Authorization": f"Token {token}"}
    cursor = None
    while True:
        params = {"cursor": cursor} if cursor else None
        response = await client.get(
            f"{DJANGO_BASE_URL}/api/users/", headers=headers, params=params
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

    Local-testing automation only: assumes Django is reachable at localhost:8000
    and reset emails land in a Mailpit instance at localhost:8025.
    """
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


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8080)
