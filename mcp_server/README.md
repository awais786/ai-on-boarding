# MCP server

Exposes tools backed by the Django API in `../sdd_django_demo/`:

- `signup` - create an account. Works even without a Django account yet.
- `request_password_reset` / `reset_password` - forgot-password flow, by email code.
- `change_my_password` - change your own password (needs an account).
- `change_user_password`, `list_signup_users`, `list_users_by_country` - admin only.

There is no signin tool: signing in with Google, below, already establishes the
credential every other tool uses.

Auth is Google login at the MCP layer, and only at the front door. A caller signs
in with Google to reach any tool; the first request of that session trades the
Google token for a Django token via `POST /api/auth/google/`, and every later
request reuses that Django token without contacting Google again. Tools call the
Django API with the caller's own token, so Django's own permission checks apply to
the real caller.

A caller Google accepts but this project issues no credential to - no account here,
or an embargoed one, indistinguishable from each other - still reaches a session,
but with no credential: every tool but `signup` refuses and tells them to sign up.
If Django later stops accepting the Django token, the Google token is exchanged
once more and the call retried; a second refusal asks the caller to sign in again.

One consequence worth knowing: because Google is not consulted mid-session,
revoking this app's Google access does not lock a caller out immediately. It takes
effect when their session credential expires, which is bounded by the Google
token's own lifetime (about an hour).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment variables

- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` - required. A Google Cloud OAuth
  client (Web application type), with `<MCP_BASE_URL>/auth/callback` added as an
  authorized redirect URI.
- `MCP_BASE_URL` - this server's own public URL, used for the Google OAuth
  callback. Defaults to `http://localhost:8100`.
- `DJANGO_API_BASE` - base URL of the Django API. Defaults to
  `http://localhost:8000/api`.
- `MCP_CREDENTIAL_CACHE_TTL_SECONDS` - ceiling on how long a credential is reused
  before the caller is verified and exchanged again. Defaults to `86400` (a day).
  It is only a ceiling: a credential also expires with the Google token it came
  from, which is sooner, so raising this does not extend a session past that.

The Django app also needs `GOOGLE_OAUTH_CLIENT_IDS` set to the same client id
(comma-separated if there are several), so `/api/auth/google/` accepts tokens
minted for it.

## Run

```bash
python server.py
```

This starts the server on `http://localhost:8100`, serving MCP over HTTP at
`http://localhost:8100/mcp`. The Django app (`../sdd_django_demo/`) needs to be
running too - see its own README - since every tool but `signup`,
`request_password_reset`, and `reset_password` calls it.

## Connect and test

### From an MCP client (Claude Desktop, Claude Code, etc.)

Point the client at `http://localhost:8100/mcp` as a remote/HTTP MCP server. The
client will prompt you through the Google sign-in on first use; there is nothing
else to configure. Consult your client's own docs for the exact "add a remote MCP
server" step - it varies by client.

### From a script, with FastMCP's own client

Useful for trying tools out or writing a quick check without a full MCP-aware
client. `auth='oauth'` drives the same Google sign-in flow through a browser
window the first time; the resulting session is then reused for later calls.

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client('http://localhost:8100/mcp', auth='oauth') as client:
        # New account - works even before signing in with a Django account
        # already on record, since signup is the one tool that doesn't need one.
        result = await client.call_tool('signup', {
            'email': 'ada@example.com',
            'username': 'ada',
            'password': 'lovelace1',
            'country': 'GB',
        })
        print(result.data)  # {'detail': 'Account created.'}

        # Self-service: change the password just set, given the current one.
        result = await client.call_tool('change_my_password', {
            'current_password': 'lovelace1',
            'new_password': 'lovelace2',
        })
        print(result.data)  # {'detail': 'Password changed.'}

        # Forgot-password flow doesn't need a session credential at all.
        result = await client.call_tool('request_password_reset', {
            'email': 'ada@example.com',
        })
        print(result.data)  # the generic "if that address has an account..." message

asyncio.run(main())
```

`list_signup_users`, `list_users_by_country`, and `change_user_password` work the
same way, but need an admin account signed in - a non-admin caller gets a clear
refusal rather than any user data.

### Trying a refusal

Calling a credentialed tool (anything but `signup`, `request_password_reset`, or
`reset_password`) before signing up returns a clear refusal rather than partial
data:

```python
result = await client.call_tool('list_signup_users', {}, raise_on_error=False)
print(result.is_error)  # True
print(result.content[0].text)  # "No account found for this Google identity. Use the signup tool to create one."
```
