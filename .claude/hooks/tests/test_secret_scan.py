"""Tests for the secret-scan PreToolUse hook.

Invokes the hook script the same way Claude Code does: JSON describing the
tool call is written to stdin, and any block decision comes back as JSON on
stdout.

Fixture strings below are built by concatenating short pieces rather than
written as one literal. That's not stylistic: this repo's own secret-scan
hook inspects file content on every Write, so a realistic-looking secret
sitting whole in this file's source would get this very edit blocked. Runtime
concatenation keeps the *value* the hook under test sees fully realistic
while keeping no single on-disk literal secret-shaped.
"""

import json
import os
import unittest

from hook_test_case import HookTestCase

HOOK = os.path.join(os.path.dirname(os.path.dirname(__file__)), "secret-scan.py")


class SecretScanHookTest(HookTestCase):
    hook_path = HOOK

    def assert_blocked(self, stdout):
        self.assertTrue(stdout, "expected a block decision, got no output")
        decision = json.loads(stdout)
        output = decision["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        return output["permissionDecisionReason"]

    def test_blocks_aws_access_key(self):
        fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"
        stdout = self.run_hook("Bash", command=f"export AWS_KEY={fake_key}")
        reason = self.assert_blocked(stdout)
        self.assertIn("AWS Access Key ID", reason)

    def test_blocks_github_token(self):
        fake_token = "gh" + "p_" + "a" * 36
        stdout = self.run_hook("Write", "/repo/notes.txt", content=f"token: {fake_token}")
        self.assert_blocked(stdout)

    def test_blocks_private_key_block(self):
        fake_block = "-----BEGIN " + "RSA PRIVATE KEY-----"
        stdout = self.run_hook("Write", "/repo/key.txt", content=fake_block)
        self.assert_blocked(stdout)

    def test_blocks_quoted_json_secret_assignment(self):
        fake_secret = "sk_live_" + "abcdefghijklmnop1234"
        content = '{"api_key": "' + fake_secret + '"}'
        stdout = self.run_hook("Write", "/repo/config.json", content=content)
        reason = self.assert_blocked(stdout)
        self.assertIn("Generic Secret Assignment", reason)

    def test_blocks_high_entropy_token(self):
        fake_token = "Zk8pQ2vN9m" + "R7wL4xT1sB" + "6yH3jD5cV0"
        stdout = self.run_hook("Write", "/repo/config.py", content=f"TOKEN = '{fake_token}'")
        self.assert_blocked(stdout)

    def test_deny_reason_does_not_echo_the_matched_secret(self):
        # Even a prefix of a real secret is sensitive and could end up logged
        # or fed back into model context; the reason must name the kind of
        # secret found, never any part of its value.
        fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"
        stdout = self.run_hook("Bash", command=f"export AWS_KEY={fake_key}")
        reason = self.assert_blocked(stdout)
        self.assertNotIn(fake_key, reason)
        self.assertNotIn(fake_key[:12], reason)

    def test_allows_placeholder_value(self):
        stdout = self.run_hook("Write", "/repo/.env.example", content="API_KEY=your_api_key_here")
        self.assertEqual(stdout, "")

    def test_allows_ordinary_code(self):
        stdout = self.run_hook(
            "Write",
            "/repo/api/views.py",
            content="def health(request):\n    return Response({'status': 'ok'})\n",
        )
        self.assertEqual(stdout, "")

    def test_does_not_scan_file_path_field(self):
        # file_path is skipped even when it happens to look "secret-shaped";
        # only the tool's actual content fields should be scanned.
        fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"
        stdout = self.run_hook("Write", f"/repo/{fake_key}-file.txt", content="ordinary text")
        self.assertEqual(stdout, "")

    def test_missing_tool_input_is_allowed(self):
        stdout = self.run_hook("Write")
        self.assertEqual(stdout, "")


if __name__ == "__main__":
    unittest.main()
