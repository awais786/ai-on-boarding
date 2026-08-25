"""Tests for the protect-files PreToolUse hook.

Invokes the hook script the same way Claude Code does: JSON describing the
tool call is written to stdin, and any block decision comes back as JSON on
stdout.
"""

import json
import os
import tempfile
import unittest

from hook_test_case import HookTestCase

HOOK = os.path.join(os.path.dirname(os.path.dirname(__file__)), "protect-files.py")

BLOCKED_CASES = [
    ("Write", "/repo/.env"),
    ("Edit", "/repo/.env.production"),
    ("Edit", "/repo/.envrc"),
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


class ProtectFilesHookTest(HookTestCase):
    hook_path = HOOK

    def assert_blocked(self, stdout, expected_in_reason):
        self.assertTrue(stdout, f"expected a block decision for {expected_in_reason!r}, got no output")
        decision = json.loads(stdout)
        output = decision["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertIn(expected_in_reason, output["permissionDecisionReason"])

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
        stdout = self.run_hook("Write")
        self.assertEqual(stdout, "")

    def test_notebook_edit_uses_notebook_path(self):
        stdout = self.run_hook("NotebookEdit", notebook_path="/home/user/.ssh/notes.ipynb")
        self.assert_blocked(stdout, "/home/user/.ssh/notes.ipynb")

    def test_notebook_edit_of_normal_notebook_is_allowed(self):
        stdout = self.run_hook("NotebookEdit", notebook_path="/repo/analysis.ipynb")
        self.assertEqual(stdout, "")

    def test_symlink_named_like_a_protected_file_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, "not_sensitive.txt")
            with open(target, "w") as f:
                f.write("harmless")
            symlink_path = os.path.join(tmp_dir, ".env")
            os.symlink(target, symlink_path)

            stdout = self.run_hook("Write", symlink_path)
            self.assert_blocked(stdout, symlink_path)

    def test_symlink_pointing_at_a_protected_file_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = os.path.join(tmp_dir, ".env")
            with open(target, "w") as f:
                f.write("SECRET=1")
            symlink_path = os.path.join(tmp_dir, "config_link")
            os.symlink(target, symlink_path)

            stdout = self.run_hook("Write", symlink_path)
            self.assert_blocked(stdout, symlink_path)

    def test_bash_command_touching_protected_file_is_blocked(self):
        stdout = self.run_hook("Bash", command="cat /repo/.env")
        self.assert_blocked(stdout, "cat /repo/.env")

    def test_bash_redirect_with_no_space_is_blocked(self):
        stdout = self.run_hook("Bash", command="echo SECRET=1>/repo/.env")
        self.assert_blocked(stdout, "echo SECRET=1>/repo/.env")

    def test_bash_command_touching_normal_file_is_allowed(self):
        stdout = self.run_hook("Bash", command="cat /repo/api/views.py")
        self.assertEqual(stdout, "")

    def test_bash_quoted_prose_mentioning_a_protected_name_is_allowed(self):
        # A commit message or echoed sentence that merely *mentions* a
        # protected-looking filename is not a file access and must not block.
        stdout = self.run_hook(
            "Bash", command='git commit -m "document the .env* pattern and .envrc handling"'
        )
        self.assertEqual(stdout, "")

    def test_bash_heredoc_body_mentioning_a_protected_name_is_allowed(self):
        command = (
            "git commit -m \"$(cat <<'EOF'\n"
            "Broaden the .env* pattern to also match .envrc\n"
            "EOF\n"
            ")\""
        )
        stdout = self.run_hook("Bash", command=command)
        self.assertEqual(stdout, "")

    def test_bash_redirect_inside_heredoc_command_is_still_allowed_when_not_a_real_redirect(self):
        # Sanity check that quoting a redirect-looking example doesn't get
        # mis-read as an actual write once it's inside the opaque span.
        command = "echo \"example: echo x>.env is dangerous\" > /tmp/notes.txt"
        stdout = self.run_hook("Bash", command=command)
        self.assertEqual(stdout, "")


if __name__ == "__main__":
    unittest.main()
