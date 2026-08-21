#!/usr/bin/env python3
"""PreToolUse hook: block Bash/Write/Edit calls whose input contains a likely secret.

Reads the hook JSON payload from stdin, extracts the text relevant to the tool being
called, and scans it against a list of known secret/token patterns. On a match, emits
a PreToolUse deny decision on stdout so Claude Code blocks the call before it runs.
"""
import json
import re
import sys

PATTERNS = [
    ("AWS access key ID", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("AWS secret access key (assignment)", re.compile(
        r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("Slack token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI-style API key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("Private key block", re.compile(
        r"-----BEGIN (RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    ("Bearer token", re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.=]{20,}")),
    ("Generic API key / secret / token assignment", re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)"
        r"\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{16,}")),
]


def extract_text(tool_name, tool_input):
    if tool_name == "Bash":
        return tool_input.get("command", "")
    if tool_name in ("Write",):
        return tool_input.get("content", "")
    if tool_name == "Edit":
        # Scan both sides - a secret being introduced OR left behind matters.
        return "\n".join([
            tool_input.get("new_string", ""),
            tool_input.get("old_string", ""),
        ])
    # Fallback: scan every string value in the input, for any other tool.
    return "\n".join(str(v) for v in tool_input.values() if isinstance(v, str))


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return  # malformed input - fail open, do not block on a parse error

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    text = extract_text(tool_name, tool_input)

    for label, pattern in PATTERNS:
        match = pattern.search(text)
        if match:
            snippet = match.group(0)
            redacted = snippet[:6] + "…" + snippet[-4:] if len(snippet) > 12 else "…"
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Blocked: input looks like it contains a {label} "
                        f"({redacted}). Remove the secret before retrying."
                    ),
                },
                "systemMessage": f"🔒 Blocked a {tool_name} call - likely {label} detected.",
            }))
            return

    # No match - stay silent so Claude Code proceeds normally.


if __name__ == "__main__":
    main()
