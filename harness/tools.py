"""Tool implementations.

Each tool is a plain callable. This module says what a tool does; it has no
say in whether the harness permits calling it — the dispatcher decides that
against the configured allowlist. `WebFetch` is registered here but absent
from the default allowlist, which shows denial keys off the config rather
than off whether a tool exists in the registry.

The allowlist gates *dispatch*, not capability: `Bash` runs arbitrary
commands, so a shell command can still reach what a denied tool would have
done. Command-level sandboxing is deliberately out of scope.
"""
from __future__ import annotations

import glob as _glob
import re
import subprocess


def tool_read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def tool_glob(pattern: str) -> list[str]:
    return sorted(_glob.glob(pattern, recursive=True))


def tool_grep(pattern: str, path: str) -> list[str]:
    regex = re.compile(pattern)
    with open(path, "r", encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f if regex.search(line)]


def tool_edit(path: str, old_string: str, new_string: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old_string not in content:
        raise ValueError(f"old_string not found in {path}")
    content = content.replace(old_string, new_string, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def tool_write(path: str, content: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return content


def tool_bash(command: str) -> str:
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=30
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        detail = output.strip()
        raise RuntimeError(
            f"command exited {result.returncode}: {detail}" if detail
            else f"command exited {result.returncode} with no output"
        )
    return output


def tool_webfetch(url: str) -> str:
    raise NotImplementedError("WebFetch has no real implementation in this toy harness")


TOOL_REGISTRY = {
    "Read": tool_read,
    "Glob": tool_glob,
    "Grep": tool_grep,
    "Edit": tool_edit,
    "Write": tool_write,
    "Bash": tool_bash,
    "WebFetch": tool_webfetch,
}
