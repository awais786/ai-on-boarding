#!/usr/bin/env python3
"""PreToolUse hook: blocks tool calls that would read or modify sensitive /
protected files (env files, credential stores, private keys, production
settings), while leaving normal source-code files untouched."""

import json
import os
import re
import sys


# Filenames (basename only) that are always protected, wherever they live.
PROTECTED_BASENAME_PATTERNS = [
    re.compile(r"^\.env(\..+)?$"),  # .env, .env.local, .env.production, ...
    re.compile(r"^credentials\.(json|ya?ml)$", re.IGNORECASE),
    re.compile(r"^secrets\.(json|ya?ml)$", re.IGNORECASE),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$"),
    re.compile(r".*\.pem$", re.IGNORECASE),
    re.compile(r".*\.pfx$", re.IGNORECASE),
    re.compile(r".*\.p12$", re.IGNORECASE),
    # production_settings.py / prod_settings.py / settings_production.py / prod.py under settings/
    re.compile(r"^(prod(uction)?[_-]?settings|settings[_-]?prod(uction)?)\.py$", re.IGNORECASE),
]

# Full-path fragments for files whose own name doesn't give it away, e.g.
# myproject/settings/production.py or config/production.py.
PROTECTED_PATH_FRAGMENTS = [
    re.compile(r"(^|/)settings/production\.py$"),
    re.compile(r"(^|/)config/production\.py$"),
]

# Directories that are protected wholesale (extend as needed per machine/project).
PROTECTED_DIRS = [
    os.path.expanduser("~/Desktop/Agnetic-workflows-learning/testing-hooks/secrets"),
    os.path.expanduser("~/crawling-framework"),
    os.path.expanduser("~/SandboxArbisoft"),
]

MUTATING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def is_protected(real_path):
    basename = os.path.basename(real_path)

    for pattern in PROTECTED_BASENAME_PATTERNS:
        if pattern.match(basename):
            return True

    for pattern in PROTECTED_PATH_FRAGMENTS:
        if pattern.search(real_path):
            return True

    for protected_dir in PROTECTED_DIRS:
        protected_dir = os.path.realpath(protected_dir)
        if real_path == protected_dir or real_path.startswith(protected_dir + os.sep):
            return True

    return False


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception as exc:
        print(f"protect-files hook: failed to parse input, allowing: {exc}", file=sys.stderr)
        return

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path")

    if not file_path:
        return

    real_path = os.path.realpath(os.path.expanduser(file_path))

    if not is_protected(real_path):
        return

    action = "modify" if tool_name in MUTATING_TOOLS else "access"
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Blocked: {tool_name} may not {action} protected file "
                        f"'{file_path}'. It matches a sensitive-file pattern "
                        "(env file, credential store, private key, or production "
                        "settings) and is off-limits to automated edits."
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    main()
