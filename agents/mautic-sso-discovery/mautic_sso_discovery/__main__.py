"""Entrypoints:
`python -m mautic_sso_discovery discover --target-repo <url> --out <path>`
`python -m mautic_sso_discovery propose-issues --report <path> --github-repo <owner>/<name>`

Local dev only: ANTHROPIC_API_KEY/BOARD_TOKEN come from real environment
secrets in CI; .env is a no-op there (the file doesn't exist).
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from issue_reconciler.client import GitHubClient

from mautic_sso_discovery.discover import run_discover
from mautic_sso_discovery.propose_issues import run_propose_issues

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _discover(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory() as workdir:
        run_discover(args.target_repo, Path(args.out), Path(workdir))
    print(f"discovery report written to {args.out}")
    return 0


def _propose_issues(args: argparse.Namespace) -> int:
    client = GitHubClient(os.environ["BOARD_TOKEN"])
    urls = run_propose_issues(Path(args.report), args.github_repo, client)
    for title, url in urls.items():
        print(f"{title}: {url}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="mautic_sso_discovery")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover")
    discover_parser.add_argument("--target-repo", required=True)
    discover_parser.add_argument("--out", required=True)
    discover_parser.set_defaults(func=_discover)

    propose_parser = subparsers.add_parser("propose-issues")
    propose_parser.add_argument("--report", required=True)
    propose_parser.add_argument("--github-repo", required=True)
    propose_parser.set_defaults(func=_propose_issues)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
