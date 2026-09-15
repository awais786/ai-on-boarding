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

4. **Check review status before opening the PR.** This repo's documented workflow (`README.md`, `openspec/config.yaml`, `CLAUDE.md`) requires `/code-review` to have returned `Ready to merge: yes` before a pull request is opened — findings only block if they cite a requirement, a named failing test, or a documented convention, and review runs at most two passes (an initial pass, one follow-up). Ask the user whether review has already been run and passed. **Do not run `/code-review` yourself without asking first** — it has a real token cost the user prefers to control themselves. If they say review hasn't happened, offer to run it before proceeding rather than opening the PR anyway.

5. **Write a lean PR description**: a short "What changed" summary and the issue reference. Cut unnecessary detail — this repo's convention is lean PR descriptions, not exhaustive ones.

6. **Create the PR** with `gh pr create` (pushing the branch first if needed), then return the PR URL to the user.

## Project standards this skill enforces

- **Every change has a matching GitHub issue** (`openspec/config.yaml` context) — the PR should reference it, not just the code change.
- **Review gate before merge**: `/code-review` must return `Ready to merge: yes`, per the review contract in `openspec/config.yaml`/`CLAUDE.md` — a `no` verdict or no review at all means the PR shouldn't be opened yet (or should be marked draft).
- **`pytest` passes for the whole project** before a change is considered done (`openspec/config.yaml` operations.archive.guidance) — worth a quick check before opening the PR, not just before archiving.
- **Lean PR descriptions** — this repo's convention (and the user's stated preference) is to cut unnecessary detail, not write an exhaustive changelog.
