#!/usr/bin/env python3
"""PreToolUse hook: blocks tool calls that would read or modify sensitive /
protected files (env files, credential stores, private keys, cloud/CLI
credential files, production settings), while leaving normal source-code
files untouched.

This file is shared and versioned with the project, so it only encodes
patterns that are broadly applicable to any developer working in this repo.
To additionally protect directories specific to your own machine (e.g. an
unrelated client project living outside this repo), add a second hook in a
gitignored `.claude/hooks/local/` script wired through `.claude/settings.local.json`
rather than hardcoding personal paths here.
"""

import json
import os
import re
import sys


# Filenames (basename only) that are always protected, wherever they live.
PROTECTED_BASENAME_PATTERNS = [
    re.compile(r"^\.env(\..+)?$"),  # .env, .env.local, .env.production, ...
    re.compile(r"^credentials\.(json|ya?ml)$", re.IGNORECASE),
    re.compile(r"^secrets?\.(json|ya?ml)$", re.IGNORECASE),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$"),
    re.compile(r".*\.pem$", re.IGNORECASE),
    re.compile(r".*\.pfx$", re.IGNORECASE),
    re.compile(r".*\.p12$", re.IGNORECASE),
    re.compile(r".*\.key$", re.IGNORECASE),  # generic private-key extension
    re.compile(r"^\.npmrc$"),  # may hold registry auth tokens
    re.compile(r"^\.pypirc$"),  # PyPI upload credentials
    re.compile(r"^\.netrc$"),  # machine login/password pairs
    re.compile(r"^\.git-credentials$"),
    re.compile(r"^kubeconfig$", re.IGNORECASE),
    # production_settings.py / prod_settings.py / settings_production.py
    re.compile(r"^(prod(uction)?[_-]?settings|settings[_-]?prod(uction)?)\.py$", re.IGNORECASE),
]

# Full-path fragments for files/dirs whose own basename doesn't give it away,
# e.g. myproject/settings/production.py, ~/.ssh/whatever, ~/.aws/credentials.
PROTECTED_PATH_FRAGMENTS = [
    re.compile(r"(^|/)settings/production\.py$"),
    re.compile(r"(^|/)config/production\.py$"),
    re.compile(r"(^|/)\.ssh/"),
    re.compile(r"(^|/)\.aws/(credentials|config)$"),
    re.compile(r"(^|/)\.kube/config$"),
    re.compile(r"(^|/)\.docker/config\.json$"),
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
                        "(env file, credential store, private key, CLI/cloud "
                        "credentials, or production settings) and is off-limits "
                        "to automated edits."
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    main()
