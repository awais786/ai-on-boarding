"""Every read-only tool, grouped by domain.

Field masking lives here rather than in backend_client (a transport concern,
not a visibility one) - see _mask_fields. If a second tool ever needs the
same masking, pull it into a shared module instead of importing it from here.
"""

from backend_client import AuthedBackendClient
from session import _call_backend, _require_backend_token

MASKED_VALUE = '***'  # real on the way in from backend_client, masked on the way out here


def load_tools(mcp):
    mcp.tool()(list_signup_users)
    mcp.tool()(list_users_by_country)


def _mask_fields(rows, masks):
    """fastmcp has no built-in for masking specific output field values - its
    output_schema only shapes the result's JSON Schema, tool_transform only
    renames/reshapes arguments, and mask_error_details redacts error text,
    not tool results - so this is applied by hand, at the read boundary,
    before a row ever reaches a caller. `masks` is a `{field: replacement}`
    mapping."""
    return [{**row, **masks} for row in rows]


# --- Users: listing signed-up users (admin only) -----------------------------
#
# Every tool below that returns a row with 'username' MUST pass it through
# _mask_fields before returning - nothing else enforces that, since masking
# isn't done centrally (see the module docstring above).


async def list_signup_users():
    """List every signed-up user (username, country, signup date). Admin only."""
    _require_backend_token()
    rows = await _call_backend(AuthedBackendClient.list_users)
    return _mask_fields(rows, {'username': MASKED_VALUE})


async def list_users_by_country(country: str):
    """List signed-up users from a specific country. Admin only."""
    _require_backend_token()
    rows = await _call_backend(AuthedBackendClient.list_users, country=country)
    return _mask_fields(rows, {'username': MASKED_VALUE})
