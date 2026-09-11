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

## Layout

- `server.py` - wiring only: builds the FastMCP app, the Google auth provider,
  and the `/secrets/{token}` route; registers the tools.
- `tools/` - the MCP tools themselves, one module per domain (`account.py`,
  `users.py`), each self-registering its own tools. Not split further into
  read vs write within a domain - each tool already carries its own
  `readOnlyHint`/`destructiveHint` annotation (see `load_tools` in either
  file), which is what actually decides whether Claude can call it without
  asking; a matching file split would only restate that, not add anything.
- `clients/` - the HTTP clients that talk to the Django API, one module per domain
  (`account_client.py`, `users_client.py`) plus shared transport plumbing in
  `base_client.py`. A tool module only imports the client for its own domain, so
  e.g. `tools/account.py` has no way to reach `UsersClient.change_password`
  through it.
- `auth.py` - verifying Google identity (`BackendGoogleProvider`, the JWT
  claims) and calling the backend with the caller's own credential
  (`call_backend`, `require_backend_token` - the stale-credential retry).
  Used to be `auth/credentials.py` + `auth/backend_calls.py`; merged into one
  file once there was no longer a good reason for two - see below.
- `elicitation.py` - collecting a secret from a human directly, never through
  the MCP protocol, client, or model: the hosted page itself (`register`,
  `get`, `discard`, the `/secrets/<token>` HTML) and the tool-side wait for a
  submission (`await_secret`, including the handshake-era fallback;
  `ElicitationError`, since that failure is specific to this concern). Used
  to be `elicitation/secret_pages.py` + `elicitation/wait_for_secret.py`,
  merged for the same reason as `auth.py`.
- `middleware.py` - request logging, used by both domains, not specific to
  either. Not (yet) its own package - see its own docstring.
- `validation.py` - domain rules checked before spending a round trip on a
  call the backend would reject anyway (currently just password strength).
  Defines its own `ValidationError` - not in `clients/`, since nothing here
  talks to the backend.
- `config.py` - every environment-driven or tunable value this server uses
  (base URLs, timeouts, TTLs, poll intervals), in one place, plus
  `load_dotenv()` itself. Without this, each of those tends to get added as
  a bare `os.environ.get(...)` in whichever module first needs it - which is
  exactly what had happened here, and which caused a real bug: `server.py`
  called `load_dotenv()` after its own imports, so any module it imported
  that read an env var at import time (`elicitation.py`'s `MCP_BASE_URL`,
  `clients/base_client.py`'s `BACKEND_API_BASE`) read it before the `.env`
  file had been loaded, silently ignoring a `.env`-only override.
  `config.py` calls `load_dotenv()` itself, before reading anything, and is
  the first of these modules every other one imports.

`auth.py` and `elicitation.py` were each two files in their own package
(`auth/credentials.py` + `auth/backend_calls.py`, `elicitation/secret_pages.py`
+ `elicitation/wait_for_secret.py`) before being flattened. The split inside
each pair was real - "verify identity" vs. "call the backend with the result"
inside `auth`; "the hosted page" vs. "waiting on it" inside `elicitation` -
but a whole package (a directory, an `__init__.py`, two files) was more
structure than two closely-related files needed, and it had a real cost: the
two packages both ended up with a file called `session.py` at one point
(different jobs, same name, because both were "the second file in a
two-file package about X"), which forced every caller to alias both imports
just to tell them apart. One file per concern, named for the concern, needs
no alias and no package machinery to say the same thing.

No shared `errors.py`. Each error type is defined where it's raised -
`BackendAPIError` in `clients/base_client.py`, `ElicitationError` in
`elicitation.py`, `ValidationError` in `validation.py` - and imported from
there by anything that needs to catch it. A shared module made sense only if
something needed to catch *any* tool error generically; nothing does, so it
was one file existing to hold an unused common base class.

`elicitation.py` is named that, not `secrets.py` - that would shadow the
standard library's own `secrets` module (used for token generation in this
same file). This project is installed as an editable package (see Setup,
below) specifically so a name like this can't silently shadow anything
installed, or be shadowed by it.

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
pip install -e . --no-deps
```

The second command registers this project itself as an editable-installed package
(`pyproject.toml`), so `auth`, `clients`, `elicitation`, `tools`, etc. are
importable from anywhere - not only when the current directory happens to be
`mcp_server/` (the failure mode that made `mcp/` and `secrets/` unsafe package
names earlier - see Layout, above). `--no-deps` skips re-resolving dependencies:
`requirements.txt` already pins the exact, tested versions (including
transitive ones); `pyproject.toml`'s `dependencies` list exists for readability
and for `pip install -e .` to work in a fresh environment, not to override
`requirements.txt`'s pins.

## Environment variables

Every environment-driven value lives in `config.py` - that file is the source of
truth for defaults; this list is just where to set them.

- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` - required, no default (read in
  `server.py`, not `config.py` - see that module's own docstring for why). A
  Google Cloud OAuth client (Web application type), with
  `<MCP_BASE_URL>/auth/callback` added as an authorized redirect URI.
- `MCP_BASE_URL` - this server's own public URL, used for the Google OAuth
  callback and every hosted secret-entry page link. Defaults to
  `http://localhost:8100`.
- `BACKEND_API_BASE` - base URL of the backend API (the Django app in this
  repo). Defaults to `http://localhost:8000/api`.
- `BACKEND_REQUEST_TIMEOUT` - seconds before a backend request times out.
  Defaults to `10`.
- `SECRET_PAGE_TTL_SECONDS` - how long a hosted secret-entry page link stays
  valid before it expires. Defaults to `900` (15 minutes).
- `HANDSHAKE_ERA_POLL_SECONDS` - poll interval for the handshake-era
  elicitation fallback (older MCP clients only). Defaults to `1`.
- `MCP_TOOL_CALL_LOG_FILE` - path to the tool-call audit log. Defaults to
  `tool_calls.log` next to this project's own files.

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
`server.py`, rendered by `elicitation.py`). Neither the value nor its page ever
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
