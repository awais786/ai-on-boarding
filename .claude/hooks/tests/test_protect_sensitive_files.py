"""Tests for protect-sensitive-files.py, the PreToolUse hook that blocks edits to
protected files.

Runs the hook as a real subprocess (stdin JSON in, stdout JSON out) rather than
importing it, since that is exactly how Claude Code invokes it.
"""
import json
import subprocess
import sys
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent.parent / "protect_sensitive_files.py"


def run_hook(payload):
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result


def deny_payload(tool_name, file_path, **extra_input):
    return {
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path, **extra_input},
    }


def assert_blocked(result, file_path):
    assert result.returncode == 0
    output = json.loads(result.stdout)
    hook_output = output["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    assert file_path in hook_output["permissionDecisionReason"]


def assert_allowed(result):
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# --- Blocked cases ---


def test_blocks_write_to_dotenv():
    result = run_hook(deny_payload("Write", ".env"))
    assert_blocked(result, ".env")


def test_blocks_edit_to_nested_dotenv_variant():
    result = run_hook(deny_payload("Edit", "config/.env.production"))
    assert_blocked(result, "config/.env.production")


def test_blocks_write_to_production_settings():
    result = run_hook(
        deny_payload("Write", "sdd_django_demo/sdd_django_demo/production_settings.py")
    )
    assert_blocked(result, "sdd_django_demo/sdd_django_demo/production_settings.py")


def test_blocks_write_to_settings_production_path():
    result = run_hook(deny_payload("Write", "myapp/settings/production.py"))
    assert_blocked(result, "myapp/settings/production.py")


def test_blocks_write_under_secrets_directory():
    result = run_hook(deny_payload("Write", "secrets/api_key.txt"))
    assert_blocked(result, "secrets/api_key.txt")


def test_blocks_write_to_credentials_file():
    result = run_hook(deny_payload("Write", "config/gcp_credentials.json"))
    assert_blocked(result, "config/gcp_credentials.json")


def test_blocks_write_to_ssh_private_key():
    result = run_hook(deny_payload("Write", "/home/user/.ssh/id_rsa"))
    assert_blocked(result, "/home/user/.ssh/id_rsa")


def test_blocks_write_to_pem_file():
    result = run_hook(deny_payload("Write", "certs/server.pem"))
    assert_blocked(result, "certs/server.pem")


def test_blocks_write_to_netrc():
    result = run_hook(deny_payload("Write", ".netrc"))
    assert_blocked(result, ".netrc")


def test_edit_uses_old_and_new_string_input_but_is_still_blocked():
    result = run_hook(
        deny_payload("Edit", ".env", old_string="A=1", new_string="A=2")
    )
    assert_blocked(result, ".env")


# --- Allowed cases ---


def test_allows_edit_to_source_file():
    result = run_hook(deny_payload("Edit", "sdd_django_demo/api/views.py"))
    assert_allowed(result)


def test_allows_write_to_dotenv_example():
    result = run_hook(deny_payload("Write", ".env.example"))
    assert_allowed(result)


def test_allows_write_to_readme():
    result = run_hook(deny_payload("Write", "README.md"))
    assert_allowed(result)


def test_allows_write_to_regular_settings_file():
    result = run_hook(deny_payload("Write", "sdd_django_demo/sdd_django_demo/settings.py"))
    assert_allowed(result)


def test_ignores_non_file_tools():
    result = run_hook({"tool_name": "Bash", "tool_input": {"command": "cat .env"}})
    assert_allowed(result)


def test_fails_open_on_malformed_json():
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input="not valid json{{{",
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_fails_open_on_missing_file_path():
    result = run_hook({"tool_name": "Write", "tool_input": {}})
    assert_allowed(result)
