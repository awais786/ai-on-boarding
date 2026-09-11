"""MCP server exposing signup-reporting tools backed by this project's backend API.

Google authenticates a caller once; the first request of a session trades that
for this project's own backend token, reused for later requests. Tools call
the backend with the caller's own token, not a blanket service credential.

This module is wiring only - auth/caching logic lives in auth/, elicitation
and the hosted secret pages live in elicitation/, the domain HTTP clients
live in clients/, the tools themselves live in tools/ (organized by domain,
account and users), and every environment-driven value lives in config.py.
"""

import os

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse

from auth import BackendGoogleProvider
from config import MCP_BASE_URL, MCP_HOST, MCP_PORT
from elicitation import get as get_pending, render_done, render_error, render_form, render_gone
from middleware import ToolCallLogger
from tools import load_tools

auth = BackendGoogleProvider(
    client_id=os.environ['GOOGLE_CLIENT_ID'],
    client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
    base_url=MCP_BASE_URL,
    required_scopes=['openid', 'email'],
)

mcp = FastMCP('user-account-reporting', auth=auth)

mcp.add_middleware(ToolCallLogger())

load_tools(mcp)


@mcp.custom_route('/secrets/{token}', methods=['GET', 'POST'])
async def secret_page(request):
    """The page every `await_secret` URL points at - an ordinary HTTP route a
    browser loads directly, not part of the MCP protocol (SEP-1036)."""
    token = request.path_params['token']
    pending = get_pending(token)
    if pending is None or pending.is_resolved:
        return HTMLResponse(render_gone(), status_code=404)

    if request.method == 'GET':
        return HTMLResponse(render_form(token, pending.fields))

    form = await request.form()
    values = {name: form.get(name, '') for name, _ in pending.fields}
    missing = [label for name, label in pending.fields if not values.get(name)]
    if missing:
        return HTMLResponse(
            render_form(token, pending.fields, error=f"{', '.join(missing)} required."),
            status_code=400,
        )

    await pending.submit(values)
    if pending.error is not None:
        return HTMLResponse(render_error(pending.error), status_code=400)
    return HTMLResponse(render_done())


if __name__ == '__main__':
    # Browser-based clients (MCP Inspector, web-hosted clients) call this server
    # cross-origin; the SDK's own OAuth discovery routes wrap CORS themselves,
    # but the /mcp transport route doesn't, so it's added here.
    cors = Middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=['WWW-Authenticate'],
    )
    mcp.run(transport='http', host=MCP_HOST, port=MCP_PORT, middleware=[cors])
