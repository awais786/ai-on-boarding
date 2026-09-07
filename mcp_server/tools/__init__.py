"""Tool registration, split by domain. Each submodule self-registers via its own
load_tools(mcp); this package's load_tools(mcp) just calls all of them."""

from . import account, users


def load_tools(mcp):
    users.load_tools(mcp)
    account.load_tools(mcp)
