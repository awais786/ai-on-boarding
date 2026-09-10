"""One agent invocation: run it, and read what the agent reported back.

The agent's --output-format json carries more than its answer. It also says
which model actually served the request and which tool calls were denied, so
the harness can report the policy's real effect rather than assuming the
flags it passed were honoured.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field


@dataclass
class AgentResult:
    ok: bool
    text: str
    cost_usd: float = 0.0
    turns: int = 0
    models: list[str] = field(default_factory=list)
    denials: list = field(default_factory=list)
    error: str | None = None


def parse_result(stdout: str) -> AgentResult:
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return AgentResult(
            ok=False, text=stdout, error="agent did not return parseable JSON"
        )

    return AgentResult(
        ok=not payload.get("is_error", False),
        text=payload.get("result") or "",
        cost_usd=payload.get("total_cost_usd") or 0.0,
        turns=payload.get("num_turns") or 0,
        models=sorted(payload.get("modelUsage") or {}),
        denials=payload.get("permission_denials") or [],
        error=payload.get("api_error_status"),
    )


def run(command: list[str], cwd: str, timeout: int = 1800) -> AgentResult:
    proc = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )
    result = parse_result(proc.stdout)
    if proc.returncode != 0 and result.ok:
        return AgentResult(
            ok=False,
            text=result.text,
            error=f"agent exited {proc.returncode}: {proc.stderr.strip()[:200]}",
        )
    return result
