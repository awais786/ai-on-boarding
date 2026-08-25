"""Tests for the pylint-check PostToolUse hook.

Invokes the hook script the same way Claude Code does: JSON describing the
edited file is written to stdin. A "decision": "block" reply on stdout means
Pylint findings would be fed back to Claude; empty stdout means the hook
allowed the turn to proceed silently.
"""

import json
import os
import shutil
import tempfile
import unittest

from hook_test_case import HookTestCase

HOOK = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pylint-check.py")

# Mirrors pylint-check.py's own PYLINT_BIN fallback: prefer the Homebrew
# install, then whatever "pylint" resolves to on PATH.
PYLINT_AVAILABLE = bool(
    os.path.exists("/opt/homebrew/bin/pylint") or shutil.which("pylint")
)


class PylintCheckHookTest(HookTestCase):
    hook_path = HOOK
    timeout = 30

    @unittest.skipUnless(PYLINT_AVAILABLE, "pylint is not installed on this machine")
    def test_python_file_with_lint_errors_is_fed_back(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as tmp:
            tmp.write("def foo():\n    return undefined_variable\n")
            path = tmp.name
        try:
            stdout = self.run_hook("Write", path)
            self.assertTrue(stdout, "expected pylint findings to be reported")
            decision = json.loads(stdout)
            self.assertEqual(decision["decision"], "block")
            self.assertIn("undefined-variable", decision["reason"])
            self.assertIn(path, decision["reason"])
        finally:
            os.unlink(path)

    @unittest.skipUnless(PYLINT_AVAILABLE, "pylint is not installed on this machine")
    def test_clean_python_file_produces_no_output(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as tmp:
            tmp.write('"""Trivial module."""\n\n\ndef add(a, b):\n    return a + b\n')
            path = tmp.name
        try:
            stdout = self.run_hook("Write", path)
            self.assertEqual(stdout, "")
        finally:
            os.unlink(path)

    def test_non_python_file_is_skipped(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            tmp.write("this is not python and would fail to parse as such (((\n")
            path = tmp.name
        try:
            stdout = self.run_hook("Write", path)
            self.assertEqual(stdout, "")
        finally:
            os.unlink(path)

    def test_nonexistent_python_file_produces_no_output(self):
        stdout = self.run_hook("Write", "/tmp/does-not-exist-hopefully.py")
        self.assertEqual(stdout, "")


if __name__ == "__main__":
    unittest.main()
