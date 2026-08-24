#!/usr/bin/env python3
"""PreToolUse hook: blocks tool calls whose inputs look like they contain
secrets, API keys, access tokens, or other credential-like strings."""

import json
import math
import re
import sys


SECRET_PATTERNS = [
    ("AWS Access Key ID", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("AWS Secret Access Key", re.compile(
        r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"
    )),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("Slack Token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,48}")),
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("Stripe Key", re.compile(r"(?:sk|rk|pk)_(live|test)_[0-9a-zA-Z]{16,}")),
    ("Twilio API Key", re.compile(r"SK[0-9a-fA-F]{32}")),
    ("Slack Webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/]{20,}")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{10,}")),
    ("Private Key Block", re.compile(r"-----BEGIN[ A-Z]*PRIVATE KEY-----")),
    ("Bearer Token", re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}=*")),
    ("Generic Secret Assignment", re.compile(
        r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token"
        r"|client[_-]?secret|password|passwd|pwd)\b\s*[=:]\s*"
        r"['\"][^'\"\s]{12,}['\"]"
    )),
]

# Fields we never need to scan: they hold paths/patterns, not secret material.
SKIP_KEYS = {"file_path", "path", "pattern", "glob", "cwd", "notebook_path"}

# Substrings that indicate an obvious placeholder rather than a real secret.
PLACEHOLDER_HINTS = (
    "your_api_key", "changeme", "xxxxxxxx", "placeholder", "example",
    "insert_key_here", "dummy", "fake", "sample", "redacted", "<key>",
    "<token>", "0000000000",
)

TOKEN_CANDIDATE = re.compile(r"[A-Za-z0-9_\-/+]{24,}")

ENTROPY_THRESHOLD = 4.3
MIN_TOKEN_LEN = 24


def shannon_entropy(s):
    if not s:
        return 0.0
    freq = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in freq.values())


def looks_like_placeholder(token):
    lowered = token.lower()
    return any(hint in lowered for hint in PLACEHOLDER_HINTS)


def find_high_entropy_tokens(text):
    findings = []
    for match in TOKEN_CANDIDATE.finditer(text):
        token = match.group(0)
        if len(token) < MIN_TOKEN_LEN or looks_like_placeholder(token):
            continue
        has_digit = any(c.isdigit() for c in token)
        has_upper = any(c.isupper() for c in token)
        has_lower = any(c.islower() for c in token)
        if sum([has_digit, has_upper, has_lower]) < 2:
            continue
        if shannon_entropy(token) >= ENTROPY_THRESHOLD:
            findings.append(token)
    return findings


def scan_text(text):
    hits = []
    for label, pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match and not looks_like_placeholder(match.group(0)):
            hits.append(f"{label} (matched: {match.group(0)[:12]}...)")
    for token in find_high_entropy_tokens(text):
        hits.append(f"Suspicious high-entropy token (possible secret): {token[:12]}...")
    return hits


def iter_strings(value, key=None):
    if isinstance(value, str):
        if key not in SKIP_KEYS:
            yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from iter_strings(v, key=k)
    elif isinstance(value, list):
        for v in value:
            yield from iter_strings(v, key=key)


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception as exc:
        print(f"secret-scan hook: failed to parse input, allowing: {exc}", file=sys.stderr)
        return

    tool_input = input_data.get("tool_input", {})

    all_hits = []
    seen = set()
    for text in iter_strings(tool_input):
        for hit in scan_text(text):
            if hit not in seen:
                seen.add(hit)
                all_hits.append(hit)

    if not all_hits:
        return

    reason = (
        "Blocked: tool input appears to contain secrets or credential-like "
        "values:\n- " + "\n- ".join(all_hits)
    )

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
