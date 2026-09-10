"""A harness around an existing coding agent (Claude Code).

The harness supplies the task, applies an execution policy, lets the agent
change the repository, then validates and judges the result. It is not an
agent runtime: the agent is Claude Code, invoked as a subprocess.

- policy.py    the execution policy, expressed as the agent's own CLI flags
- validate.py  the project's tests, run after the agent finishes
- __main__.py  the task -> agent -> validation -> verdict slice
"""
