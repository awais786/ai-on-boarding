"""Every call that leaves this tool for GitHub, in one place - a single
place to stub in tests and to answer "what does this bot do to a repo".
"""
from __future__ import annotations

import json
import subprocess


class GitHubError(RuntimeError):
    pass


def _gh_json(*args: str):
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise GitHubError(f"gh {' '.join(args)} failed: {result.stderr}")
    return json.loads(result.stdout)


def pr_comments(repo: str, pr: str) -> list[dict]:
    return _gh_json("api", f"repos/{repo}/issues/{pr}/comments")


def pr_file_blobs(repo: str, pr: str) -> dict[str, str]:
    """Path -> blob SHA for every file in the PR. Content-addressed, so it
    survives rebase and force-push where a commit range would not.
    """
    files = _gh_json("api", f"repos/{repo}/pulls/{pr}/files", "--paginate")
    return {f["filename"]: f["sha"] for f in files if "sha" in f}


def update_comment(repo: str, comment_id, body: str) -> None:
    # capture_output: `gh api` echoes the whole comment object on success,
    # which would dump several KB into the CI log every run.
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/comments/{comment_id}", "-X", "PATCH", "--input", "-"],
        input=json.dumps({"body": body}), text=True, capture_output=True,
    )
    if result.returncode != 0:
        raise GitHubError(f"updating comment {comment_id} failed: {result.stderr}")


def pr_review_comments(repo: str, pr: str) -> list[dict]:
    """Inline (file/line-anchored) comments, as opposed to pr_comments()'s
    conversation-level ones. Used to avoid re-posting a finding every push.
    """
    return _gh_json("api", f"repos/{repo}/pulls/{pr}/comments", "--paginate")


def create_review_comment(repo: str, pr: str, commit_sha: str, path: str, line: int, body: str) -> None:
    """Anchor one finding to the line it is about.

    GitHub rejects a comment on a line outside the diff, so the caller must
    be ready for this to fail - the finding is still listed in the summary
    comment, which is the complete record.
    """
    payload = json.dumps({
        "body": body, "commit_id": commit_sha, "path": path,
        "line": line, "side": "RIGHT",
    })
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{pr}/comments", "--input", "-"],
        input=payload, text=True, capture_output=True,
    )
    if result.returncode != 0:
        raise GitHubError(f"inline comment on {path}:{line} failed: {result.stderr.strip()}")


def create_comment(pr: str, body: str) -> None:
    result = subprocess.run(
        ["gh", "pr", "comment", pr, "--body", body], text=True, capture_output=True,
    )
    if result.returncode != 0:
        raise GitHubError(f"posting a comment on PR {pr} failed: {result.stderr}")
