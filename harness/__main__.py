"""The vertical slice: task -> policy -> coding agent -> validation -> verdict.

Run via ./harness/run "<task>". The coding agent is Claude Code, invoked as a
subprocess; the harness supplies the task, applies the execution policy, and
judges the result afterwards. It does not participate in the agent's loop.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import subprocess
import sys

from .policy import build_agent_command, load_policy
from .validate import run_tests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def working_tree_state(repo_root: str) -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return sorted(ln for ln in proc.stdout.splitlines() if ln.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness/run",
        description="Run a coding task through the configured coding agent, then validate it.",
    )
    parser.add_argument("task", help='e.g. "Add login functionality"')
    parser.add_argument("--policy", default=None, help="path to a policy YAML file")
    parser.add_argument(
        "--model",
        default=None,
        help="run this task on a specific model, overriding the policy "
        "(alias such as opus/sonnet/haiku, or a full model name)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show the agent command and exit without invoking the agent",
    )
    args = parser.parse_args(argv)

    policy = load_policy(args.policy)
    if args.model:
        policy = dataclasses.replace(policy, model=args.model)
    command = build_agent_command(args.task, policy)

    print(f"task    : {args.task}")
    print(f"policy  : allowed_tools = {', '.join(policy.allowed_tools) or '(none)'}")
    print(f"          permission_mode = {policy.permission_mode}")
    print(f"          model = {policy.model or '(agent default)'}")
    print(f"command : {' '.join(command)}")
    print()

    if args.dry_run:
        print("dry run — agent not invoked")
        return 0

    before = working_tree_state(REPO_ROOT)

    print("running agent…")
    agent = subprocess.run(command, cwd=REPO_ROOT)
    print(f"agent exited {agent.returncode}")

    changed = [ln for ln in working_tree_state(REPO_ROOT) if ln not in before]
    print(f"changed : {len(changed)} path(s)")
    for line in changed:
        print(f"          {line}")

    print("\nvalidating…")
    validation = run_tests(REPO_ROOT)
    print(f"tests   : {validation.summary}")

    passed = agent.returncode == 0 and validation.ok
    print(f"\n{'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
