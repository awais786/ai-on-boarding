#!/usr/bin/env python3
"""PostToolUse hook: runs Pylint on a Python file after Claude edits/writes it
and feeds any findings back to Claude."""

import glob
import json
import os
import subprocess
import sys


PYLINT_BIN = "/opt/homebrew/bin/pylint"
TIMEOUT_SECONDS = 60

# Only error/fatal findings block; convention/refactor/warning are informational noise
# (missing docstrings, too-few-public-methods, etc.) that varies too much by project style.
# no-member is disabled on top of that: pylint's static analysis can't see attributes injected
# dynamically by a metaclass (Django model Managers, SQLAlchemy, attrs, ...), so it's a
# well-known high-false-positive check on any such framework, not just Django.
PYLINT_ARGS = ["--disable=C,R,W,no-member", "--score=n"]


def find_venv_site_packages(file_path):
    """Walk up from file_path looking for a .venv/venv directory and return its
    site-packages dir, so pylint can resolve that project's installed imports
    (e.g. django) without needing pylint itself installed in every venv."""
    directory = os.path.dirname(file_path)
    while True:
        for venv_name in (".venv", "venv"):
            venv_dir = os.path.join(directory, venv_name)
            matches = glob.glob(os.path.join(venv_dir, "lib", "python*", "site-packages"))
            if matches:
                return matches[0]
            windows_site_packages = os.path.join(venv_dir, "Lib", "site-packages")
            if os.path.isdir(windows_site_packages):
                return windows_site_packages
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception as exc:
        print(f"pylint-check hook: failed to parse input, skipping: {exc}", file=sys.stderr)
        return

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path")

    if not file_path or not file_path.endswith(".py"):
        return

    file_path = os.path.realpath(os.path.expanduser(file_path))

    if not os.path.isfile(file_path):
        return

    pylint_bin = PYLINT_BIN if os.path.exists(PYLINT_BIN) else "pylint"

    env = dict(os.environ)
    site_packages = find_venv_site_packages(file_path)
    if site_packages:
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = site_packages if not existing else f"{site_packages}{os.pathsep}{existing}"

    try:
        result = subprocess.run(
            [pylint_bin, *PYLINT_ARGS, file_path],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env=env,
        )
    except FileNotFoundError:
        print("pylint-check hook: pylint not found, skipping", file=sys.stderr)
        return
    except subprocess.TimeoutExpired:
        print("pylint-check hook: pylint timed out, skipping", file=sys.stderr)
        return
    except Exception as exc:
        print(f"pylint-check hook: failed to run pylint, skipping: {exc}", file=sys.stderr)
        return

    output = (result.stdout or "").strip()

    if not output:
        return

    print(
        json.dumps(
            {
                "decision": "block",
                "reason": (
                    f"Pylint reported issues in {file_path}:\n\n{output}\n\n"
                    "Please review and address these before proceeding."
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
