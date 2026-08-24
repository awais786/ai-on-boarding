"""Shared helpers for this project's Claude Code hook scripts."""
import json
import sys


def read_payload():
    """Read and parse the hook JSON payload from stdin.

    Returns None on malformed input, so callers can fail open (skip silently)
    rather than crash or block on a parse error.
    """
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None


def file_path_for(payload, file_tools):
    """Return tool_input.file_path if payload's tool_name is in file_tools, else None."""
    tool_name = payload.get("tool_name", "")
    if tool_name not in file_tools:
        return None
    tool_input = payload.get("tool_input", {}) or {}
    return tool_input.get("file_path", "")
