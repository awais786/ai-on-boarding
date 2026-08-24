"""Tests for the protect-files PreToolUse hook.

Invokes the hook script the same way Claude Code does: JSON describing the
tool call is written to stdin, and any block decision comes back as JSON on
stdout.
"""

import json
import os
import subprocess
import sys
import unittest

HOOK = os.path.join(os.path.dirname(os.path.dirname(__file__)), "protect-files.py")

BLOCKED_CASES = [
    ("Write", "/repo/.env"),
    ("Edit", "/repo/.env.production"),
    ("Write", "/repo/credentials.json"),
    ("MultiEdit", "/repo/secrets.yaml"),
    ("Write", "/home/user/.ssh/id_rsa"),
    ("Edit", "/repo/certs/server.pem"),
    ("Edit", "/repo/myproject/production_settings.py"),
    ("Write", "/repo/myproject/settings/production.py"),
    ("Read", "/repo/.env"),
    ("Read", "/home/user/.ssh/known_hosts"),
    ("Write", "/home/user/.aws/credentials"),
    ("Edit", "/home/user/.aws/config"),
    ("Write", "/repo/.npmrc"),
    ("Write", "/repo/.pypirc"),
    ("Write", "/home/user/.netrc"),
    ("Write", "/home/user/.git-credentials"),
    ("Write", "/home/user/.kube/config"),
    ("Write", "/home/user/.docker/config.json"),
    ("Write", "/repo/certs/client.key"),
]

ALLOWED_CASES = [
    ("Write", "/repo/api/views.py"),
    ("Edit", "/repo/api/models.py"),
    ("Write", "/repo/myproject/settings.py"),
    ("Write", "/repo/myproject/settings/development.py"),
    ("MultiEdit", "/repo/README.md"),
    ("Write", "/repo/src/app.js"),
]


class ProtectFilesHookTest(unittest.TestCase):
    def run_hook(self, tool_name, file_path):
        payload = {"tool_name": tool_name, "tool_input": {"file_path": file_path}}
        result = subprocess.run(
            [sys.executable, HOOK],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def assert_blocked(self, stdout, file_path):
        self.assertTrue(stdout, f"expected a block decision for {file_path!r}, got no output")
        decision = json.loads(stdout)
        output = decision["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn(file_path, output["permissionDecisionReason"])

    def test_blocks_protected_files(self):
        for tool_name, file_path in BLOCKED_CASES:
            with self.subTest(tool_name=tool_name, file_path=file_path):
                stdout = self.run_hook(tool_name, file_path)
                self.assert_blocked(stdout, file_path)

    def test_allows_normal_source_files(self):
        for tool_name, file_path in ALLOWED_CASES:
            with self.subTest(tool_name=tool_name, file_path=file_path):
                stdout = self.run_hook(tool_name, file_path)
                self.assertEqual(stdout, "")

    def test_missing_file_path_is_allowed(self):
        result = subprocess.run(
            [sys.executable, HOOK],
            input=json.dumps({"tool_name": "Write", "tool_input": {}}),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
