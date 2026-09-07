"""MCP server exposing signup-reporting tools backed by the Django API.

Google authenticates a caller once; the first request of a session trades that
for this project's own Django token, reused for later requests. Tools call
Django with the caller's own token, not a blanket service credential.

This module is wiring only - auth/caching logic lives in credentials.py,
elicitation and the Django call path live in session.py, and the tools
themselves live in tools/, organized by domain.
"""

import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.responses import HTMLResponse

import credentials
import secret_pages
import session
import tools
from mcp_middleware import ToolCallLogger, ToolCallRateLimiter

load_dotenv()

auth = credentials.DjangoGoogleProvider(
    client_id=os.environ['GOOGLE_CLIENT_ID'],
    client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
    base_url=session.MCP_BASE_URL,
    required_scopes=['openid', 'email'],
)

mcp = FastMCP('django-user-reporting', auth=auth)

mcp.add_middleware(ToolCallLogger())  # outermost, so it also logs a rate-limit rejection
mcp.add_middleware(ToolCallRateLimiter())

tools.load_tools(mcp)


@mcp.custom_route('/secrets/{token}', methods=['GET', 'POST'])
async def secret_page(request):
    """The page every `_await_secret` URL points at - an ordinary HTTP route a
    browser loads directly, not part of the MCP protocol (SEP-1036)."""
    token = request.path_params['token']
    pending = secret_pages.get(token)
    if pending is None or pending.is_resolved:
        return HTMLResponse(secret_pages.render_gone(), status_code=404)

    if request.method == 'GET':
        return HTMLResponse(secret_pages.render_form(token, pending.fields))

    form = await request.form()
    values = {name: form.get(name, '') for name, _ in pending.fields}
    missing = [label for name, label in pending.fields if not values.get(name)]
    if missing:
        return HTMLResponse(
            secret_pages.render_form(token, pending.fields, error=f"{', '.join(missing)} required."),
            status_code=400,
        )

    await pending.submit(values)
    if pending.error is not None:
        return HTMLResponse(secret_pages.render_error(pending.error), status_code=400)
    return HTMLResponse(secret_pages.render_done())


if __name__ == '__main__':
    mcp.run(transport='http', host='0.0.0.0', port=8100)
