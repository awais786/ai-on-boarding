---
name: pr-creation
description: Create a pull request for the current branch, following this repo's conventions. Use when the user asks to open, create, or file a PR.
allowed-tools: Bash(git:*), Bash(gh:*)
license: MIT
---

Create a pull request for the current branch's changes.

**Hard rule: every PR must reference the GitHub issue it addresses. If no issue can be confidently identified, stop and ask the user which issue it is before creating the PR — never guess an issue number and never open a PR with no issue link.**

## Steps

1. **Gather context.** Run `git status`, `git diff` (staged and unstaged), and `git log <base>..HEAD` to see everything the PR will contain. Confirm the base branch and target repo (this repo's upstream is `awais786/ai-on-boarding`; PRs are typically pushed to a fork first, then opened against `awais786/ai-on-boarding:main`).

2. **Find the issue this PR addresses.** Check, in this order, and stop at the first confident match:
   - The branch name (e.g. `123-fix-thing`, `fix-123`)
   - Commit messages in this branch's history (`Closes #N`, `Fixes #N`, a plain `#N` mention)
   - The current OpenSpec change's linked GitHub issue, if this branch corresponds to one (`openspec/changes/<name>/` — this repo's convention is that every change has a matching issue; see `openspec/config.yaml`)
   - Conversation context — has the user already named an issue in this session?

   **If none of these produce a confident match, ask the user which issue this PR addresses before doing anything else.** Do not proceed to PR creation on a guess.

3. **Confirm the linking keyword.** Ask the user (or infer from context) whether the PR should `Closes #N` (auto-closes the issue on merge) or `Relates to #N` (references it without closing) — don't assume `Closes` is always correct.

4. **Write a lean PR description**: a short "What changed" summary and the issue reference. Cut unnecessary detail — this repo's convention is lean PR descriptions, not exhaustive ones.

5. **Create the PR** with `gh pr create` (pushing the branch first if needed), then return the PR URL to the user.
