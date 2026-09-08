"""Tool registration, split by read vs. write. Each submodule self-registers
via its own load_tools(mcp); this package's load_tools(mcp) just calls both."""

from . import read, write


def load_tools(mcp):
    read.load_tools(mcp)
    write.load_tools(mcp)
