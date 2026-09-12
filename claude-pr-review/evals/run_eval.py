"""Phase 0 eval harness: run Layer 3 (verify.py) + Layer 4 (gate.py) against
every frozen fixture in evals/fixtures/, score the result with scorer.py,
and run the harness-level wiring checks (below). `make eval` runs this.

Fixtures are frozen artifacts - this never regenerates a fixture's diff.txt
and never reaches the network for repo content (diff.txt/rules.json/
findings.json are read as-is; snapshot/ is staged into the real repo tree
for the run and removed after - see materialize()).

Layer 1 (lint.py) and Layer 2 (judge.py) are not exercised here: both are
tightly coupled to target.py's live git/gh calls to resolve "what changed",
which a frozen fixture has no equivalent of. lint.py is pure ruff and needs
no eval; judge.py's own harness is a separate, later piece of work. What
this suite scores is the part that decides whether a citation survives and
whether the gate's verdict is right - the part Phase 1/2 change the most.

--dry-run stubs the Anthropic client so harness bugs (fixture loading,
staging, scoring, JSON shape) can be found without spending a token.
"""
# ruff: noqa: I001 - the sys.path setup below has to run before the
# sibling-module imports, which necessarily splits the import block.
from __future__ import annotations

import argparse
import json
import shutil
import sys
import types
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # claude-pr-review/ - gate.py, verify.py, etc.

import anthropic

from pr_review.core import agent
from pr_review.pipeline import gate
import scorer
from pr_review.pipeline import verify
from pr_review.core.target import REPO_ROOT

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# --- staging: put a fixture's file tree in the working tree for the run -----
#
# Folded in from what used to be fixture_tree.py, whose only caller was this
# module. Exists because Layer 3 reads the *working tree* through tools.py
# while being handed a fixture's diff - without staging, the two disagree:
# an early version of the harness ran fixtures whose diff added files that
# weren't in the worktree, so every read_file failed, Layer 3 concluded the
# described code didn't exist, and dropped findings for that reason rather
# than any reason the fixture was written to test. (Also why
# tools.execute() flags a failed read as `is_error` rather than returning
# "No such file" as ordinary content - the model was reading a tool failure
# as a fact about the repository.)

@contextmanager
def materialize(fixture_dir: Path, subdir: str = "snapshot"):
    """Stage `fixture_dir/subdir` into the repo, then remove it again.

    Refuses to touch a path that already exists - a fixture is never
    allowed to overwrite real repository content.
    """
    source_root = fixture_dir / subdir
    staged: list[Path] = []
    if not source_root.is_dir():
        print(f"[eval] {fixture_dir}/{subdir}/ missing - Layer 3 will read a tree that does not "
              f"match the fixture diff, and findings may be dropped for that reason alone.",
              file=sys.stderr)
        yield
        return

    try:
        for source in sorted(source_root.rglob("*")):
            if not source.is_file():
                continue
            destination = REPO_ROOT / source.relative_to(source_root)
            if destination.exists():
                raise FileExistsError(f"fixture would overwrite existing repo file: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            staged.append(destination)
        print(f"[eval] staged {len(staged)} fixture file(s) into {REPO_ROOT}", file=sys.stderr)
        yield
    finally:
        for path in staged:
            path.unlink(missing_ok=True)
        print(f"[eval] removed {len(staged)} staged fixture file(s)", file=sys.stderr)


# --- stub client for --dry-run ----------------------------------------------

def _stub_response(findings: list[dict] | None = None):
    payload = json.dumps({"findings": findings or []})
    return types.SimpleNamespace(
        stop_reason="end_turn",
        content=[types.SimpleNamespace(type="text", text=payload)],
    )


class _StubStream:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return _stub_response()


class _StubMessages:
    def create(self, **kwargs):
        return _stub_response()


class _StubBetaMessages:
    def stream(self, **kwargs):
        return _StubStream()


class _StubClient:
    """Fakes just enough of anthropic.Anthropic for agent.run() - always
    zero findings, whichever of the two request paths (plain vs. task-budget
    streaming) the caller takes. Exercises harness mechanics only, never
    prompt quality.
    """

    def __init__(self):
        self.messages = _StubMessages()
        self.beta = types.SimpleNamespace(messages=_StubBetaMessages())


# --- fixtures and scoring ----------------------------------------------

def load_fixture(fixture_dir: Path) -> tuple[str, dict, dict, dict]:
    diff = (fixture_dir / "diff.txt").read_text()
    rules = json.loads((fixture_dir / "rules.json").read_text())
    findings = json.loads((fixture_dir / "findings.json").read_text())
    expected = json.loads((fixture_dir / "expected.json").read_text())
    return diff, rules, findings, expected


def run_case(client, fixture_dir: Path) -> dict:
    diff, rules, findings, expected = load_fixture(fixture_dir)
    agent.reset_usage()
    with materialize(fixture_dir):
        verified = verify.verify(client, diff, rules, findings)
    _, ready = gate.render(verified)
    produced = {
        "findings": verified["findings"],
        "verdict": "yes" if ready else "no",
        "cost": {"usd": agent.USAGE["usd"]},
    }
    scored = scorer.score_case(produced, expected)
    # Surfaced per case so a cache regression is visible as a number rather
    # than as a slowly rising bill: repeated per-finding calls share a
    # diff+rules prefix, so cache_read staying at 0 means it stopped working.
    scored["usage"] = dict(agent.USAGE)
    return scored


# --- harness wiring checks (plan 4.4) ---------------------------------------
#
# Folded in from what used to be checks.py, whose only caller was this
# module. These guard wiring a fixture can't see. The one that matters
# most: the review step runs with `continue-on-error: true` so the verdict
# comment still gets posted when the answer is "no" - which means a
# *separate* step is what actually fails the check. Delete that step and
# nothing breaks loudly; the reviewer just quietly becomes advisory and
# every PR goes green forever. That is a failure mode worth a standing
# assertion rather than a code review someone might not do.
#
# Deliberately string-matched rather than YAML-parsed: pyyaml isn't a
# dependency of this tool, and adding one to assert four lines would be a
# worse trade than a handful of substring checks.

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
REVIEW_WORKFLOW = WORKFLOWS_DIR / "pr-review-agent.yml"
COLLECT_WORKFLOW = WORKFLOWS_DIR / "pr-review-collect.yml"


def _directives(path: Path) -> str:
    """The workflow's actual YAML, with comment lines removed.

    Both files explain *why* they avoid `pull_request_target` and why the
    collect half holds no write permission, so a naive substring search
    finds those strings in prose and reports the opposite of the truth.
    Inline trailing comments count too - `contents: read # never
    pull-requests: write` is a directive that says one thing and a comment
    that mentions another. A check should never pass or fail on prose.
    """
    kept = []
    for line in path.read_text().splitlines():
        if line.lstrip().startswith("#"):
            continue
        directive, _, _ = line.partition(" #")
        kept.append(directive)
    return "\n".join(kept)


def check_gate_exit_path() -> tuple[bool, str]:
    """The review step's failure must still fail the job."""
    if not REVIEW_WORKFLOW.is_file():
        return False, f"{REVIEW_WORKFLOW.name} is missing"
    text = _directives(REVIEW_WORKFLOW)

    if "id: review" not in text:
        return False, "the review step lost its `id: review`, so nothing can key off its outcome"
    if "steps.review.outcome == 'failure'" not in text:
        return False, "no step fails the job on the review step's failure - the reviewer is advisory"
    if "exit 1" not in text:
        return False, "the failure step no longer exits non-zero"
    return True, "a failing review still fails the job"


def check_fork_safety() -> tuple[bool, str]:
    """The untrusted half must stay untrusted, and the trusted half must not
    be reachable from a PR's own code.
    """
    if not COLLECT_WORKFLOW.is_file():
        return False, f"{COLLECT_WORKFLOW.name} is missing - fork PRs would run without secrets"
    collect, review = _directives(COLLECT_WORKFLOW), _directives(REVIEW_WORKFLOW)

    if "pull_request_target" in collect or "pull_request_target" in review:
        return False, "pull_request_target puts secrets in scope on a PR-controlled checkout"
    if "pull-requests: write" in collect:
        return False, "the collect workflow must not hold write permission"
    if "secrets." in collect:
        return False, "the collect workflow must not reference secrets - a fork PR never gets them"
    if "workflow_run" not in review:
        return False, "the review workflow no longer runs in the trusted workflow_run context"
    if "PR_REVIEW_RULES_ROOT" not in review:
        return False, "rules are no longer pinned to the trusted checkout - a PR could rewrite them"
    return True, "the untrusted half holds no secrets and no write access"


CHECKS = {
    "gate_exit_path": check_gate_exit_path,
    "fork_safety": check_fork_safety,
}


def run_checks() -> dict[str, dict]:
    return {name: dict(zip(("ok", "message"), check(), strict=False)) for name, check in CHECKS.items()}


# --- entrypoint --------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Stub the Anthropic client - no tokens spent")
    args = parser.parse_args()

    client = _StubClient() if args.dry_run else anthropic.Anthropic()

    fixture_dirs = sorted(d for d in FIXTURES_DIR.iterdir() if d.is_dir())
    case_scores = {fixture_dir.name: run_case(client, fixture_dir) for fixture_dir in fixture_dirs}

    check_results = run_checks()
    result = {
        "cases": case_scores,
        "summary": scorer.summarize(case_scores),
        "checks": check_results,
    }
    output = json.dumps(result, indent=2)
    print(output)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)

    # A failed harness check is a wiring regression, not a score - it means
    # something that can't be caught by scoring fixtures has broken, so it
    # fails the run outright rather than showing up as a number nobody reads.
    failed = [name for name, r in check_results.items() if not r["ok"]]
    if failed:
        for name in failed:
            print(f"[eval] CHECK FAILED {name}: {check_results[name]['message']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
