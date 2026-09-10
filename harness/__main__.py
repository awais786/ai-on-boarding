"""The vertical slice: task -> phases -> agent -> verification -> recovery -> verdict.

Run via ./harness/run "<task>". Each phase is one Claude Code invocation with
its own model and tool policy; the harness supplies the task, applies the
policy, feeds each phase's output to the next, then verifies the result and
hands failures back to the agent a bounded number of times before judging.
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
from .validate import run_checks

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def working_tree_state(repo_root: str) -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return sorted(ln for ln in proc.stdout.splitlines() if ln.strip())


def run_phase(phase, prompt: str) -> session.AgentResult:
    command = build_agent_command(prompt, phase)
    print(f"[{phase.name}]")
    print(f"  model : {phase.model or '(agent default)'}")
    print(f"  tools : {', '.join(phase.allowed_tools) or '(none)'}")

    result = session.run(command, cwd=REPO_ROOT)
    print(f"  ran on: {', '.join(result.models) or 'unreported'}")
    print(f"  turns : {result.turns}   cost: ${result.cost_usd:.4f}")
    if result.denials:
        print(f"  denied: {len(result.denials)} tool call(s) blocked by policy")
    if not result.ok:
        print(f"  error : {result.error or 'agent reported failure'}")
    print()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness/run",
        description="Run a coding task through the configured coding agent, then verify it.",
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

        def on_model(phase):
            return phase and dataclasses.replace(phase, model=args.model)

        policy = dataclasses.replace(
            policy,
            phases=[on_model(p) for p in policy.phases],
            repair=on_model(policy.repair),
        )

    if not policy.phases:
        print("policy defines no phases", file=sys.stderr)
        return 2

    print(f"task   : {args.task}")
    print(f"phases : {' -> '.join(p.name for p in policy.phases)}")
    print(f"checks : {', '.join(c.name for c in policy.checks) or '(none)'}")
    print(f"repair : up to {policy.max_repair_attempts} attempt(s)\n")

    if args.dry_run:
        for phase in policy.phases:
            command = build_agent_command(phase.render(task=args.task), phase)
            print(f"[{phase.name}]")
            print(f"  model : {phase.model or '(agent default)'}")
            print(f"  tools : {', '.join(phase.allowed_tools) or '(none)'}")
            print(f"  cmd   : {' '.join(command)}\n")
        print("dry run — agent not invoked")
        return 0

    before = working_tree_state(REPO_ROOT)
    previous = ""
    total_cost = 0.0

    for phase in policy.phases:
        result = run_phase(phase, phase.render(task=args.task, previous=previous))
        total_cost += result.cost_usd
        if not result.ok:
            print("FAIL")
            return 1
        previous = result.text

    failed: list = []
    for attempt in range(policy.max_repair_attempts + 1):
        print("verifying…")
        results = run_checks(REPO_ROOT, policy.checks)
        for check in results:
            print(f"  {'ok  ' if check.ok else 'FAIL'} {check.name}: {check.summary}")
        failed = [c for c in results if not c.ok]
        print()

        if not failed or not policy.repair or attempt == policy.max_repair_attempts:
            break

        print(f"repair attempt {attempt + 1} of {policy.max_repair_attempts}")
        failures = "\n".join(f"- {c.name}: {c.summary}" for c in failed)
        repair = run_phase(
            policy.repair, policy.repair.render(task=args.task, failures=failures)
        )
        total_cost += repair.cost_usd
        if not repair.ok:
            break

    changed = [ln for ln in working_tree_state(REPO_ROOT) if ln not in before]
    print(f"changed: {len(changed)} path(s)")
    for line in changed:
        print(f"         {line}")
    print(f"cost   : ${total_cost:.4f}")

    print(f"\n{'PASS' if not failed else 'FAIL'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
