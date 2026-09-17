#!/usr/bin/env python3
"""PreToolUse guard: refuse tool calls that touch protected files or carry secrets.

Reads a PreToolUse hook payload on stdin and writes a permission decision on stdout.

Two independent checks run against every matched tool call:

1. Protected paths - the call names a file that must not be touched. Protection comes
   in two flavours, because they need different answers for a read:

   * CONFIDENTIAL (.env, private keys, credential stores) - reading is as harmful as
     writing, because the secret ends up in the transcript. Both are refused.
   * INTEGRITY (production settings, this guard's own configuration and hook scripts)
     - the risk is modification, not disclosure. Writes are refused; reads are fine,
     so reviewing or linting these files still works.

2. Secret-looking content - the call carries a credential in its payload, either a
   recognisable provider key (sk-ant-..., AKIA..., a PEM private key block) or a
   generic ``NAME = "value"`` credential assignment.

Anything else is allowed through silently, so ordinary source edits are untouched.

Break glass: set CLAUDE_HOOKS_ALLOW_PROTECTED=1 to downgrade every block to a warning.
That escape hatch is deliberate - this guard protects its own source file, so without
it a bad edit here could only be undone outside Claude Code.
"""

from __future__ import annotations

import fnmatch
import json
import os
import posixpath
import re
import sys

BREAK_GLASS_ENV = "CLAUDE_HOOKS_ALLOW_PROTECTED"

# Why a path is protected, and therefore whether a read is allowed.
CONFIDENTIAL = "confidential"  # reading leaks the secret: refuse read and write
INTEGRITY = "integrity"  # the risk is modification: refuse writes only

# Basenames that are protected wherever they appear in the tree.
PROTECTED_BASENAMES: tuple[tuple[str, str, str], ...] = (
    (".env", "environment file", CONFIDENTIAL),
    (".env.*", "environment file", CONFIDENTIAL),
    ("*.env", "environment file", CONFIDENTIAL),
    ("secrets.py", "secrets file", CONFIDENTIAL),
    ("secrets.json", "secrets file", CONFIDENTIAL),
    ("secrets.yml", "secrets file", CONFIDENTIAL),
    ("secrets.yaml", "secrets file", CONFIDENTIAL),
    ("credentials", "credentials file", CONFIDENTIAL),
    ("credentials.json", "credentials file", CONFIDENTIAL),
    ("service-account*.json", "service account key", CONFIDENTIAL),
    (".netrc", "stored login credentials", CONFIDENTIAL),
    (".npmrc", "package registry credentials", CONFIDENTIAL),
    (".pypirc", "package registry credentials", CONFIDENTIAL),
    (".htpasswd", "password database", CONFIDENTIAL),
    ("id_rsa", "private SSH key", CONFIDENTIAL),
    ("id_dsa", "private SSH key", CONFIDENTIAL),
    ("id_ecdsa", "private SSH key", CONFIDENTIAL),
    ("id_ed25519", "private SSH key", CONFIDENTIAL),
    ("*.pem", "private key or certificate", CONFIDENTIAL),
    ("*.key", "private key", CONFIDENTIAL),
    ("*.pfx", "private key bundle", CONFIDENTIAL),
    ("*.p12", "private key bundle", CONFIDENTIAL),
    ("*.jks", "java keystore", CONFIDENTIAL),
    ("*.keystore", "java keystore", CONFIDENTIAL),
)

# Path-shaped patterns, matched against the whole path.
#
# Production settings are INTEGRITY rather than CONFIDENTIAL on the convention that
# deployed settings read their secrets from the environment rather than embedding
# them. If one does embed a secret, the content scanner below still refuses to write
# it. Reading a settings file is ordinary review work and stays allowed.
PROTECTED_PATHS: tuple[tuple[str, str, str], ...] = (
    ("*/settings/production.py", "production settings", INTEGRITY),
    ("*/settings/prod.py", "production settings", INTEGRITY),
    ("*/settings/staging.py", "deployed-environment settings", INTEGRITY),
    ("*production_settings.py", "production settings", INTEGRITY),
    ("*settings_production.py", "production settings", INTEGRITY),
    ("*prod_settings.py", "production settings", INTEGRITY),
    ("*/.aws/*", "cloud provider credentials", CONFIDENTIAL),
    ("*/.ssh/*", "SSH configuration and keys", CONFIDENTIAL),
    ("*/.gnupg/*", "GPG keyring", CONFIDENTIAL),
    ("*/.git/config", "git remote configuration", INTEGRITY),
    # Self-protection: an agent must not be able to switch its own guard off.
    # The glob covers settings.json, settings.local.json, and any other
    # settings.<name>.json - all of them can carry an `env` block, and an `env`
    # block can set this guard's own break-glass variable.
    ("*.claude/settings*.json", "Claude Code configuration", INTEGRITY),
)

# Hook scripts are executed by Claude Code on every matching tool call, so writing one
# is arbitrary code execution. Only scripts sitting directly in a .claude/hooks
# directory are covered - their tests live a level down and stay editable.
HOOKS_DIR_RE = re.compile(r"(^|/)\.claude/hooks/[^/]+\.py$")

# Recognisable credentials. These are checked in every file, tests and prose
# included - a real provider key is a leak wherever it is written.
PROVIDER_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"), "Anthropic API key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "OpenAI-style API key"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), "GitHub fine-grained token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "AWS temporary access key id"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "Google API key"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "Slack token"),
    (re.compile(r"\bxapp-\d-[A-Za-z0-9\-]{10,}"), "Slack app-level token"),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"), "GitLab personal access token"),
    (
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        "private key block",
    ),
    (
        re.compile(
            r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
        ),
        "JSON Web Token",
    ),
)

# Generic "this looks like a credential being hard-coded" heuristic.
CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"""
    \b(?P<name>[A-Za-z0-9_\-]*
        (?:SECRET|PASSWORD|PASSWD|APIKEY|API[_\-]KEY|ACCESS[_\-]?TOKEN|
           AUTH[_\-]?TOKEN|PRIVATE[_\-]?KEY|CLIENT[_\-]?SECRET|TOKEN)
       [A-Za-z0-9_\-]*)
    \s*[:=]\s*
    (?P<quote>['"])(?P<value>[^'"\n]{8,})(?P=quote)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Values that read as "fill this in later" rather than as a live credential.
PLACEHOLDER_VALUE_RE = re.compile(
    r"""
    ^(?:
        x{3,}
      | \*{3,}
      | \.{3,}
      | <[^>]*>
      | \{\{.*\}\}
      | \$\{?[A-Za-z_][A-Za-z0-9_]*\}?
      | %\([A-Za-z_][A-Za-z0-9_]*\)s
      | (?:change[_\-]?me|placeholder|example|dummy|fake|redacted|todo|none|null
          |sample|secret|password|your[_\-\s]?\w*)\S*
      | (?:os\.environ|os\.getenv|env\.|process\.env|config\(|get_secret).*
    )$
    """,
    re.IGNORECASE | re.VERBOSE,
)

TEST_PATH_RE = re.compile(r"(^|/)(tests?|testing)(/|$)|(^|/)(test_[^/]*|[^/]*_test)\.py$")

# Documentation describes credentials as often as source hard-codes them. The generic
# heuristic cannot tell an example from a live key, so prose is exempt from it - the
# provider patterns above still apply.
PROSE_SUFFIXES = frozenset({".md", ".markdown", ".rst", ".txt", ".adoc"})

# Commands that modify their path arguments. Anything else naming a path is a read.
MUTATING_COMMANDS = frozenset(
    {
        "rm", "mv", "cp", "touch", "truncate", "tee", "dd", "install", "ln", "chmod",
        "chown", "chgrp", "shred", "mkdir", "rmdir", "patch", "unzip", "gunzip",
        "vim", "vi", "nano", "emacs", "ed", "pico", "code",
    }
)
# These mutate only when asked to edit in place.
INPLACE_COMMANDS = frozenset({"sed", "perl", "ruby", "gawk"})
# These never open their arguments as files, so a filename among them is just text.
# Without this, writing `echo 'add .env to gitignore'` reads as an attempt on .env.
NON_FILESYSTEM_COMMANDS = frozenset({"echo", "printf", "true", "false", ":"})

# Commands that hand their arguments to something outside this machine. A command
# with no write destination is not putting a credential into source, so the generic
# heuristic is not the right tool for it - except here, where the text is leaving.
TRANSMITTING_COMMANDS = frozenset(
    {
        "curl", "wget", "http", "https", "httpie", "nc", "ncat", "netcat", "telnet",
        "ssh", "scp", "sftp", "rsync", "ftp", "lftp", "mail", "mailx", "sendmail",
    }
)

# Tools that open their path argument for reading only. Any other tool naming a
# path is treated as writing it, which is the safe default: a tool wrongly assumed
# to write is over-protected, one wrongly assumed to read is under-protected.
READ_ONLY_TOOLS = frozenset({"Read", "NotebookRead", "Glob", "Grep"})

SHELL_STRIP = "\"'`()[]{};|&<>=$"
# `&&` and `||` are matched before the single-character class, so a bare `&`
# still separates segments: without it `echo hi & rm <protected>` stayed one
# segment and was skipped wholesale by the echo exemption.
SEGMENT_SPLIT_RE = re.compile(r"\|\||&&|[;|&\n]")
HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
# `$(...)` and backticks. Matched innermost-first and applied repeatedly, so a
# nested substitution is unwrapped one layer at a time.
SUBSTITUTION_RE = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")


def normalise(path: str) -> str:
    """Return a posix-style path with no redundant separators."""
    return posixpath.normpath(path.replace("\\", "/"))


def is_test_path(path: str | None) -> bool:
    """True when the path is a test file or lives under a tests directory."""
    if not path:
        return False
    return bool(TEST_PATH_RE.search(normalise(path)))


def is_prose_path(path: str | None) -> bool:
    """True when the path names a documentation file rather than source."""
    if not path:
        return False
    return posixpath.splitext(normalise(path))[1].lower() in PROSE_SUFFIXES


def protection_for(path: str | None) -> tuple[str, str] | None:
    """Return (description, mode) when ``path`` is protected, else None."""
    if not path:
        return None
    normalised = normalise(path)
    basename = posixpath.basename(normalised)
    for pattern, description, mode in PROTECTED_BASENAMES:
        if fnmatch.fnmatch(basename, pattern):
            return description, mode
    for pattern, description, mode in PROTECTED_PATHS:
        if fnmatch.fnmatch(normalised, pattern) or fnmatch.fnmatch(
            "/" + normalised.lstrip("/"), pattern
        ):
            return description, mode
    if HOOKS_DIR_RE.search(normalised):
        return "a Claude Code hook script", INTEGRITY
    return None


def protected_reason(path: str | None, *, writing: bool = True) -> str | None:
    """Return why ``path`` may not be accessed this way, or None when it may.

    A read of an INTEGRITY-protected path is allowed; a read of a CONFIDENTIAL one
    is not, because the contents would land in the transcript.
    """
    found = protection_for(path)
    if found is None:
        return None
    description, mode = found
    if not writing and mode == INTEGRITY:
        return None
    article = "" if description.startswith(("a ", "an ", "the ")) else "a protected "
    verb = "written" if writing else "read"
    return f"{normalise(path)} is {article}{description} and must not be {verb}"


def fixture_destinations(paths) -> bool:
    """True when every destination is a test file or a prose file.

    *Every*, not *any*: a command that writes a fixture and a source file in one go
    must not be exempted by the fixture half. An empty list is not exempt either -
    text going nowhere in particular gets the strict reading.
    """
    named = [path for path in paths if path]
    return bool(named) and all(is_test_path(p) or is_prose_path(p) for p in named)


def secret_reason(text: str | None, *, paths=(), scan_generic: bool = True) -> str | None:
    """Return why ``text`` looks like it carries a credential, or None."""
    if not text:
        return None
    for pattern, label in PROVIDER_SECRET_PATTERNS:
        if pattern.search(text):
            article = "n" if label[0] in "AEIOU" else ""
            return f"content contains what looks like a{article} {label}"
    # The generic heuristic fires on literals like PASSWORD = "hunter2000", which is
    # how test fixtures are written and how documentation shows examples. Skip it for
    # both; the provider patterns above still apply there.
    if not scan_generic or fixture_destinations(paths):
        return None
    for match in CREDENTIAL_ASSIGNMENT_RE.finditer(text):
        value = match.group("value").strip()
        if PLACEHOLDER_VALUE_RE.match(value):
            continue
        return (
            f"content assigns a literal credential to {match.group('name')!r} "
            "(hard-coded secrets belong in the environment, not in source)"
        )
    return None


def strip_heredocs(command: str) -> str:
    """Remove heredoc bodies, which are data rather than arguments.

    Without this, writing a document that merely mentions a protected filename is
    read as an attempt to open that file.
    """
    for match in HEREDOC_RE.finditer(command):
        terminator = match.group(2)
        body = re.compile(
            r"(" + re.escape(match.group(0)) + r".*?\n).*?^\s*" + re.escape(terminator) + r"\s*$",
            re.DOTALL | re.MULTILINE,
        )
        command = body.sub(r"\1", command, count=1)
    return command


def split_substitutions(command: str) -> tuple[str, list[str]]:
    """Return the command with substitution bodies lifted out, plus those bodies.

    A command substitution really does open the files it names, so its body has to
    be classified on its own. Left inline, it was covered by whatever command word
    started the segment - so the `echo`/`printf` exemption skipped it entirely and
    `echo $(cat .env)` printed a confidential file into the transcript while a bare
    `cat .env` was refused.
    """
    bodies: list[str] = []

    def lift(match: re.Match[str]) -> str:
        bodies.append(match.group(1) if match.group(1) is not None else match.group(2))
        return " "

    previous = None
    while previous != command:  # repeat so nested substitutions unwrap innermost first
        previous = command
        command = SUBSTITUTION_RE.sub(lift, command)
    return command, bodies


def classify_segment(
    segment: str, writes: list[str], reads: list[str], *, in_substitution: bool = False
) -> None:
    """Sort one command segment's paths into ``writes`` and ``reads``.

    Substitution bodies are classified by the same rules as anything else. An
    earlier version treated everything inside `$(...)` as a read, which stopped
    `echo $(cat .env)` leaking a secret but let `echo $(rm <guard>)` through -
    integrity-protected paths allow reads, so that handed an agent a way to delete
    its own guard. The command word decides intent here as it does anywhere else.
    """
    cleaned, redirect_targets = split_redirects(segment)
    writes.extend(t for t in redirect_targets if t)
    if not cleaned:
        return

    command_word = posixpath.basename(cleaned[0])
    # The echo/printf exemption is for text that is never opened. Inside a
    # substitution the point is to run something and capture it, so it does not
    # apply - that exemption is what swallowed `echo $(cat .env)`.
    if not in_substitution and command_word in NON_FILESYSTEM_COMMANDS:
        return
    if in_substitution:
        # `$(<secret)` has no command word at all, so the first token may itself be
        # a path. A real program name will not match a protected glob.
        reads.append(cleaned[0])

    arguments = [t for t in cleaned[1:] if not t.startswith("-")]
    flags = [t for t in cleaned[1:] if t.startswith("-")]
    mutating = command_word in MUTATING_COMMANDS or (
        command_word in INPLACE_COMMANDS and any(f.startswith("-i") for f in flags)
    )
    (writes if mutating else reads).extend(arguments)


def split_redirects(segment: str) -> tuple[list[str], list[str]]:
    """Split one command segment into its ordinary words and its redirect targets.

    A redirect target is a write however benign the command looks, which is why it
    is separated before the command word is consulted at all.
    """
    cleaned: list[str] = []
    redirect_targets: list[str] = []
    expecting_redirect = False

    for raw in (t for t in re.split(r"\s+", segment.strip()) if t):
        if re.fullmatch(r"[0-9]*(>>?|<)&?[0-9]*", raw):
            expecting_redirect = raw.lstrip("0123456789").startswith(">")
            continue
        glued = re.match(r"^[0-9]*(>>?)(.+)$", raw)
        if glued:
            redirect_targets.append(glued.group(2).strip(SHELL_STRIP))
            continue
        token = raw.strip(SHELL_STRIP)
        if not token:
            continue
        if expecting_redirect:
            redirect_targets.append(token)
            expecting_redirect = False
            continue
        cleaned.append(token)

    return cleaned, redirect_targets


def command_words(command: str):
    """Yield the leading word of every segment, substitution bodies included."""
    outer, bodies = split_substitutions(strip_heredocs(command))
    for text in [outer, *bodies]:
        for segment in SEGMENT_SPLIT_RE.split(text):
            cleaned, _ = split_redirects(segment)
            if cleaned:
                yield posixpath.basename(cleaned[0])


def transmits(command: str) -> bool:
    """True when any part of the command sends data off the machine."""
    return any(word in TRANSMITTING_COMMANDS for word in command_words(command))


def classify_bash_paths(command: str) -> tuple[list[str], list[str]]:
    """Split a shell command into the paths it writes and the paths it only reads."""
    writes: list[str] = []
    reads: list[str] = []

    outer, bodies = split_substitutions(strip_heredocs(command))

    for segment in SEGMENT_SPLIT_RE.split(outer):
        classify_segment(segment, writes, reads)
    for body in bodies:
        for segment in SEGMENT_SPLIT_RE.split(body):
            classify_segment(segment, writes, reads, in_substitution=True)

    return writes, reads


def targets_and_text(tool_name: str, tool_input: dict) -> tuple[list[str], list[str], list[str]]:
    """Split a tool input into paths written, paths read, and text carried."""
    written: list[str] = []
    read: list[str] = []
    texts: list[str] = []

    # Tools that only ever open a path for reading. Everything else naming a path
    # is treated as writing it. Without this split the read/write flavours were
    # dead outside Bash: every file_path counted as a write, so a Read of an
    # integrity-protected file was refused as though it were an edit.
    destination = read if tool_name in READ_ONLY_TOOLS else written
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            destination.append(value)

    for key in ("content", "new_string", "old_string", "new_source", "command"):
        value = tool_input.get(key)
        if isinstance(value, str):
            texts.append(value)

    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            for key in ("new_string", "old_string"):
                value = edit.get(key)
                if isinstance(value, str):
                    texts.append(value)

    if tool_name == "Bash":
        command = tool_input.get("command")
        if isinstance(command, str):
            bash_writes, bash_reads = classify_bash_paths(command)
            written.extend(bash_writes)
            read.extend(bash_reads)

    return written, read, texts


def evaluate(payload: dict) -> str | None:
    """Return a block reason for this hook payload, or None to allow it."""
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None

    written, read, texts = targets_and_text(tool_name, tool_input)

    for path in written:
        reason = protected_reason(path, writing=True)
        if reason:
            return f"{tool_name} was blocked: {reason}."
    for path in read:
        reason = protected_reason(path, writing=False)
        if reason:
            return f"{tool_name} was blocked: {reason}."

    # Where this text is headed decides whether the fixture exemption applies. Only
    # the path-carrying tools name a destination directly; a Bash command names its
    # own, in the redirect and command targets `written` already holds. Without this,
    # a Bash payload was scanned with no path at all, so the exemption could never
    # fire for a heredoc: `cat > test_x.py` was refused while `Write` to that same
    # path was allowed.
    named = [tool_input.get(k) for k in ("file_path", "notebook_path")]
    destinations = [p for p in named if p] or written
    display_path = destinations[0] if len(destinations) == 1 else None

    # A shell command that writes nowhere is not hard-coding anything, and the
    # generic heuristic reads its arguments as though it were: `grep "SECRET = " x.py`
    # was refused for containing the pattern it was searching for. Searching, listing
    # and reading are not writing. The exception is a command that sends the text
    # somewhere - there the payload matters even though no file changes - and the
    # provider patterns still apply either way, so a real key cannot ride this out.
    scan_generic = True
    if tool_name == "Bash" and not written:
        scan_generic = transmits(tool_input.get("command") or "")

    for text in texts:
        reason = secret_reason(text, paths=destinations, scan_generic=scan_generic)
        if reason:
            where = f" to {display_path}" if display_path else ""
            return f"{tool_name}{where} was blocked: {reason}."

    return None


def deny(reason: str) -> dict:
    """Build the deny decision Claude Code acts on."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{reason}\n\nIf this is genuinely intended, ask the user to make the "
                f"change themselves, or re-run with {BREAK_GLASS_ENV}=1 set."
            ),
        },
        "systemMessage": f"Blocked by protect_sensitive_files: {reason}",
    }


def warn(reason: str) -> dict:
    """Build the break-glass warning shown instead of a block."""
    return {"systemMessage": f"{BREAK_GLASS_ENV} is set - allowing despite: {reason}"}


def decide(payload: dict) -> dict | None:
    """Map a payload to the JSON this hook should emit, or None to stay silent."""
    try:
        reason = evaluate(payload)
    # A guard that fails open is not a guard: any unexpected error becomes a denial.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        reason = f"the protect_sensitive_files guard failed to evaluate this call ({exc})"
    if reason is None:
        return None
    if os.environ.get(BREAK_GLASS_ENV) == "1":
        return warn(reason)
    return deny(reason)


def main() -> int:
    """Read a hook payload from stdin and write any decision to stdout."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    output = decide(payload)
    if output is not None:
        json.dump(output, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
