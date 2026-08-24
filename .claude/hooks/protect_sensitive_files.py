#!/usr/bin/env python3
"""PreToolUse hook: block Write/Edit calls that target a protected file.

Reads the hook JSON payload from stdin, checks the target file path against a list of
protected patterns (dotenv files, production settings, credentials, private keys), and
on a match emits a PreToolUse deny decision on stdout so Claude Code blocks the call
before it runs. Everything else - ordinary source-code edits - proceeds untouched.

Scope: only tools with a structured `file_path` in tool_input (Write, Edit) are checked.
A Bash command that writes to a protected path (e.g. `cat > .env`) is not covered here.
"""
import json
import re

from _hook_common import file_path_for, read_payload

FILE_TOOLS = {"Write", "Edit"}

# (pattern, human-readable label). Matched with re.search against the file path, so `/`
# anchors are relative to any path segment boundary, not just the repo root.
PROTECTED_PATTERNS = [
    (re.compile(r'(^|/)\.env(\.[^/]*)?$'), 'a dotenv file'),
    (re.compile(r'(^|/)(production|prod)[_.-]?settings\.py$'), 'a production settings file'),
    (re.compile(r'(^|/)settings[/.](production|prod)\.py$'), 'a production settings file'),
    (re.compile(r'(^|/)secrets(/|$)'), 'a file under a secrets/ directory'),
    (re.compile(r'(^|/)[^/]*credentials[^/]*\.(json|ya?ml|ini|txt)$'), 'a credentials file'),
    (re.compile(r'(^|/)\.(aws|azure)/credentials$'), 'a cloud provider credentials file'),
    (re.compile(r'(^|/)\.netrc$'), 'a .netrc credentials file'),
    (re.compile(r'(^|/)\.npmrc$'), 'a .npmrc file (may hold auth tokens)'),
    (re.compile(r'(^|/)(id_rsa|id_ed25519|id_ecdsa|id_dsa)(\.pub)?$'), 'an SSH key file'),
    (re.compile(r'\.(pem|key|pfx|p12)$'), 'a private key or certificate file'),
]

# Basenames containing any of these are treated as safe-to-edit templates, not real
# secrets, even if they'd otherwise match a protected pattern (e.g. `.env.example`).
ALLOWLIST_HINTS = ('example', 'sample', 'template', '.dist')


def find_match(file_path):
    """Return a human-readable label if file_path matches a protected pattern, else None."""
    if not file_path:
        return None
    basename = file_path.rsplit('/', 1)[-1].lower()
    if any(hint in basename for hint in ALLOWLIST_HINTS):
        return None
    for pattern, label in PROTECTED_PATTERNS:
        if pattern.search(file_path):
            return label
    return None


def main():
    """Deny the pending Write/Edit if its target file is protected; else stay silent."""
    payload = read_payload()
    if payload is None:
        return

    file_path = file_path_for(payload, FILE_TOOLS)
    if not file_path:
        return

    label = find_match(file_path)
    if label is None:
        return

    tool_name = payload.get("tool_name", "")
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked: '{file_path}' looks like {label}. Editing protected files "
                f"is not allowed by this project's PreToolUse hook. If this file "
                f"genuinely needs to change, ask the user to edit it directly."
            ),
        },
        "systemMessage": f"\U0001f512 Blocked {tool_name} on a protected file: {file_path}",
    }))


if __name__ == "__main__":
    main()
