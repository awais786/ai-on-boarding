"""Every environment-driven or tunable value this server uses, in one place -
base URLs, timeouts, TTLs, poll intervals - so a new one doesn't get added as
a bare `os.environ.get(...)` call in whichever module happens to need it
first. This is where to look to see every knob this server has, and the only
place their defaults should be changed.

Google's client id/secret are deliberately not here: they have no default,
so reading them is what actually stops the server from starting without
them. Reading them here would make importing this module - for a timeout
value, say - fail without Google credentials too, when nothing about a
timeout has anything to do with Google. They're read directly in server.py,
the one place that genuinely can't run without them.

`load_dotenv()` runs here, not in server.py, and before anything below reads
an env var - it has to run before the *first* os.environ read anywhere in
the process, and this module is the first thing every other module that
reads one imports.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- This MCP server's own public URL, used for the Google OAuth callback
# and every hosted secret-entry page link. ---
MCP_BASE_URL = os.environ.get('MCP_BASE_URL', 'http://localhost:8100')

# --- What this process itself binds to. Defaults suit running it directly;
# behind a reverse proxy terminating TLS, set MCP_HOST=127.0.0.1 so the
# plaintext port isn't also reachable directly. ---
MCP_HOST = os.environ.get('MCP_HOST', '0.0.0.0')
MCP_PORT = int(os.environ.get('MCP_PORT', '8100'))

# --- Backend API (clients/) ---
BACKEND_API_BASE = os.environ.get('BACKEND_API_BASE', 'http://localhost:8000/api')
BACKEND_REQUEST_TIMEOUT = float(os.environ.get('BACKEND_REQUEST_TIMEOUT', '10'))

# --- Elicitation (elicitation/) ---
SECRET_PAGE_TTL_SECONDS = int(os.environ.get('SECRET_PAGE_TTL_SECONDS', 15 * 60))  # a human might take a while to open the link
HANDSHAKE_ERA_POLL_SECONDS = float(os.environ.get('HANDSHAKE_ERA_POLL_SECONDS', '1'))

# --- Middleware ---
TOOL_CALL_LOG_FILE = os.environ.get(
    'MCP_TOOL_CALL_LOG_FILE', os.path.join(os.path.dirname(__file__), 'tool_calls.log')
)
