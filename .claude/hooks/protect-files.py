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
    re.compile(r"^\.env"),  # .env, .env.local, .env.production, .envrc, ...
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

# Bash has no file_path; a protected path can appear anywhere in the command text
# (e.g. `cat .env`, `cp id_rsa /tmp/`, `echo x > .env`). Split on whitespace and shell
# control characters so redirection targets show up as their own token even when
# written with no surrounding space (`echo x>.env`).
COMMAND_TOKEN_SPLIT = re.compile(r"[\s;|&<>]+")

# Quoted strings and heredoc bodies are free-text payloads (a commit message, a
# file's new content), not path arguments — scanning them word-by-word would
# treat any prose that happens to mention a protected filename as a hit. Blank
# each one out to a single opaque placeholder before tokenizing, so real
# unquoted shell syntax (the actual redirects/arguments) is still scanned.
QUOTE_OR_HEREDOC_START = re.compile(r"""(['"])|<<-?\s*(['"]?)(\w+)\2""")


def is_protected(path):
    basename = os.path.basename(path)

    for pattern in PROTECTED_BASENAME_PATTERNS:
        if pattern.match(basename):
            return True

    for pattern in PROTECTED_PATH_FRAGMENTS:
        if pattern.search(path):
            return True

    return False


def strip_free_text_payloads(command):
    """Blank out quoted strings and heredoc bodies to a single opaque token each,
    leaving unquoted shell syntax untouched. Best-effort, not a full shell
    parser: a quote embedded inside a payload (e.g. a commit message quoting a
    value) can end the span early, in which case the remainder is scanned as
    if it were ordinary command text — matching this hook's normal behavior
    rather than silently allowing it through."""
    out = []
    i, n = 0, len(command)
    while i < n:
        match = QUOTE_OR_HEREDOC_START.search(command, i)
        if not match:
            out.append(command[i:])
            break
        out.append(command[i:match.start()])

        quote = match.group(1)
        if quote:
            end = command.find(quote, match.end())
            if end == -1:
                out.append(command[match.start():])
                break
            out.append(" _OPAQUE_ ")
            i = end + 1
            continue

        delimiter = match.group(3)
        body_start = command.find("\n", match.end())
        end_match = None
        if body_start != -1:
            end_pattern = re.compile(rf"^[ \t]*{re.escape(delimiter)}[ \t]*$", re.MULTILINE)
            end_match = end_pattern.search(command, body_start + 1)
        if end_match is None:
            out.append(command[match.start():])
            break
        out.append(command[match.start():match.end()])
        out.append(" _OPAQUE_ ")
        i = end_match.end()
    return "".join(out)


def command_candidate_paths(command):
    scrubbed = strip_free_text_payloads(command)
    tokens = (t.strip("'\"") for t in COMMAND_TOKEN_SPLIT.split(scrubbed) if t)
    return [os.path.expanduser(t) for t in tokens]


def target_paths(tool_name, tool_input):
    """Every path string this tool call could touch, in the form it should be
    checked in. For file-path tools this includes both the path as given (so a
    protected basename is still caught even if it's a symlink to somewhere
    innocuous) and its resolved real path (so a symlink *to* a protected file is
    also caught)."""
    if tool_name == "Bash":
        return command_candidate_paths(tool_input.get("command", ""))

    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return []

    requested_path = os.path.expanduser(file_path)
    return [requested_path, os.path.realpath(requested_path)]


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception as exc:
        print(f"protect-files hook: failed to parse input, allowing: {exc}", file=sys.stderr)
        return

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if not any(is_protected(path) for path in target_paths(tool_name, tool_input)):
        return

    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if tool_name == "Bash":
        action = "run a command touching"
        target = tool_input.get("command", "")
    else:
        action = "modify" if tool_name in MUTATING_TOOLS else "access"
        target = file_path

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Blocked: {tool_name} may not {action} protected file "
                        f"'{target}'. It matches a sensitive-file pattern "
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
