"""MCP server exposing signup-reporting tools backed by this project's backend API.

Google authenticates a caller once; the first request of a session trades that
for this project's own backend token, reused for later requests. Tools call
the backend with the caller's own token, not a blanket service credential.

This module is wiring only - auth/caching logic lives in credentials.py,
elicitation and the backend call path live in session.py, and the tools
themselves live in tools/, organized by domain and by read vs. write.
"""

import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.responses import HTMLResponse

from credentials import BackendGoogleProvider
from mcp_middleware import ToolCallLogger
from secret_pages import get as get_pending, render_done, render_error, render_form, render_gone
from session import MCP_BASE_URL
from tools import load_tools

load_dotenv()

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
    """The page every `_await_secret` URL points at - an ordinary HTTP route a
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
    mcp.run(transport='http', host='0.0.0.0', port=8100)
