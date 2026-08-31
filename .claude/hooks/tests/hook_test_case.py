"""Shared base class for the hook tests: invokes a hook script the same way
Claude Code does (JSON describing the tool call piped to stdin) and hands back
whatever it wrote to stdout."""

import json
import subprocess
import sys
import unittest


class HookTestCase(unittest.TestCase):
    hook_path = None  # set by subclasses to the script under test
    timeout = 10

    def run_hook(self, tool_name, file_path=None, **extra_tool_input):
        tool_input = dict(extra_tool_input)
        if file_path is not None:
            tool_input["file_path"] = file_path
        payload = {"tool_name": tool_name, "tool_input": tool_input}
        result = subprocess.run(
            [sys.executable, self.hook_path],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()
