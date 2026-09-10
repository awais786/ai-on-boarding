"""The vertical slice: task -> phases -> agent -> validation -> verdict.

Run via ./harness/run "<task>". Each phase is one Claude Code invocation with
its own model and tool policy; the harness supplies the task, applies the
policy, feeds each phase's output to the next, then validates and judges.
It does not participate in the agent's loop.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import subprocess
import sys

from . import session
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
        help="run every phase on this model, overriding the policy "
        "(alias such as opus/sonnet/haiku, or a full model name)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show each phase's command and exit without invoking the agent",
    )
    args = parser.parse_args(argv)

    policy = load_policy(args.policy)
    if args.model:
        policy = dataclasses.replace(
            policy,
            phases=[dataclasses.replace(p, model=args.model) for p in policy.phases],
        )

    if not policy.phases:
        print("policy defines no phases", file=sys.stderr)
        return 2

    print(f"task   : {args.task}")
    print(f"phases : {' -> '.join(p.name for p in policy.phases)}\n")

    before = working_tree_state(REPO_ROOT)
    previous = ""
    total_cost = 0.0

    for phase in policy.phases:
        prompt = phase.render(args.task, previous)
        command = build_agent_command(prompt, phase)

        print(f"[{phase.name}]")
        print(f"  model : {phase.model or '(agent default)'}")
        print(f"  tools : {', '.join(phase.allowed_tools) or '(none)'}")

        if args.dry_run:
            print(f"  cmd   : {' '.join(command)}\n")
            continue

        result = session.run(command, cwd=REPO_ROOT)
        total_cost += result.cost_usd
        print(f"  ran on: {', '.join(result.models) or 'unreported'}")
        print(f"  turns : {result.turns}   cost: ${result.cost_usd:.4f}")
        if result.denials:
            print(f"  denied: {len(result.denials)} tool call(s) blocked by policy")
        if not result.ok:
            print(f"  error : {result.error or 'agent reported failure'}")
            print("\nFAIL")
            return 1
        print()
        previous = result.text

    if args.dry_run:
        print("dry run — agent not invoked")
        return 0

    changed = [ln for ln in working_tree_state(REPO_ROOT) if ln not in before]
    print(f"changed: {len(changed)} path(s)")
    for line in changed:
        print(f"         {line}")

    print("\nvalidating…")
    validation = run_tests(REPO_ROOT)
    print(f"tests  : {validation.summary}")
    print(f"cost   : ${total_cost:.4f}")

    print(f"\n{'PASS' if validation.ok else 'FAIL'}")
    return 0 if validation.ok else 1


if __name__ == "__main__":
    sys.exit(main())
