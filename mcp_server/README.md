# MCP server

Exposes tools backed by the Django API in `../sdd_django_demo/`:

- `signup` - create an account. Works even without a Django account yet.
- `request_password_reset` / `reset_password` - forgot-password flow, by email code.
- `change_my_password` - change your own password (needs an account).
- `change_user_password` (admin only), `list_signup_users`, `list_users_by_country`.

None of `signup`, `reset_password`, `change_my_password`, or `change_user_password`
take a password as a tool argument: your MCP client collects each one directly from
you, so the calling assistant never sees any of them - see "Elicited passwords"
below.

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
window the first time; the resulting session is then reused for later calls. Every
password-setting tool collects its password(s) on a page this server itself hosts
rather than taking them as arguments - see "Elicited passwords" below for what
that means for a script.

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client('http://localhost:8100/mcp', auth='oauth') as client:
        # New account - works even before signing in with a Django account
        # already on record, since signup is the one tool that doesn't need one.
        # The password itself is never in this call - it's entered on the page
        # the tool opens; a real client opens it for you automatically.
        result = await client.call_tool('signup', {
            'email': 'ada@example.com',
            'username': 'ada',
            'country': 'GB',
        })
        print(result.data)  # {'detail': 'Account created.'}

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

### Elicited passwords

`signup`, `reset_password`, `change_my_password`, and `change_user_password` take
no password as a tool argument. The MCP spec forbids collecting a secret through
form-mode elicitation (the client would render it inline, with nothing stopping it
reaching the model too) - so each of these tools instead uses **URL-mode
elicitation** (SEP-1036): the server hands the caller a URL, and the human enters
the password directly on a page this server hosts (`/secrets/<token>` in
`server.py`, rendered by `secret_pages.py`). Neither the value nor its page ever
passes through the MCP protocol, the client, or the model - only this process and
the human's own browser see it. A real MCP client (Claude Desktop, Claude Code)
opens that URL for you automatically; there's nothing extra to configure.

A script using FastMCP's `Client` needs an `elicitation_handler` to know what to
do with the URL - a real one would open it in a browser and wait for the human;
a script can simulate that human by POSTing the page directly:

```python
import httpx2
from fastmcp.client.elicitation import ElicitResult

async def handler(message, response_type, params, ctx):
    # response_type is None for URL-mode elicitation - there's no schema, only
    # params.url, exactly like the link a real client would open in a browser.
    async with httpx2.AsyncClient() as http:
        await http.post(params.url, data={'password': 'lovelace1'})
    return ElicitResult(action='accept')  # acknowledges completion; carries no value

async with Client('http://localhost:8100/mcp', auth='oauth', elicitation_handler=handler) as client:
    result = await client.call_tool('signup', {'email': 'ada@example.com', 'username': 'ada', 'country': 'GB'})
    print(result.data)  # {'detail': 'Account created.'}
```

`change_my_password` is the one exception worth knowing about: its page has two
fields (current password, then new), collected in a single visit rather than two
separate rounds, so the same handler above needs both keys in one POST:

```python
async def handler(message, response_type, params, ctx):
    async with httpx2.AsyncClient() as http:
        await http.post(params.url, data={'current_password': 'lovelace1', 'new_password': 'lovelace2'})
    return ElicitResult(action='accept')

async with Client('http://localhost:8100/mcp', auth='oauth', elicitation_handler=handler) as client:
    result = await client.call_tool('change_my_password', {})
    print(result.data)  # {'detail': 'Password changed.'}
```

### Trying a refusal

Calling a credentialed tool (anything but `signup`, `request_password_reset`, or
`reset_password`) before signing up returns a clear refusal rather than partial
data:

```python
result = await client.call_tool('list_signup_users', {}, raise_on_error=False)
print(result.is_error)  # True
print(result.content[0].text)  # "No account found for this Google identity. Use the signup tool to create one."
```
