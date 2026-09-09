# Claude PR Review (GitHub Action)

Runs the real Claude Code CLI, headless, inside GitHub Actions - not a custom script calling the
API. `claude-pr-review.yml` reviews every PR (`opened`, `synchronize`) using this repo's own
review contract (`openspec/config.yaml`, `CLAUDE.md`) as the prompt, and posts the result as PR
comments via `gh pr comment` / inline review comments.

This is the alternative to the standalone Python agent on the `pr-review-agent` branch: same
goal, but delegated to Anthropic's [`claude-code-action`](https://github.com/anthropics/claude-code-action)
instead of hand-rolled orchestration.

## One-time setup

1. Install the Claude GitHub App on this repo (repo admin required):
   ```
   claude /install-github-app
   ```
   or follow [docs/setup.md](https://github.com/anthropics/claude-code-action/blob/main/docs/setup.md)
   for a manual app + secret setup.

2. Generate a subscription OAuth token locally (Pro/Max plan - uses subscription quota, not API
   billing):
   ```
   claude setup-token
   ```

3. Add it as a repo secret named `CLAUDE_CODE_OAUTH_TOKEN`
   (Settings -> Secrets and variables -> Actions -> New repository secret).

4. Open a PR. The workflow runs automatically on `opened`/`synchronize`.

## Why this shape

- **Real Claude Code, not a reimplementation.** The action checks out the repo and runs the
  actual CLI, so it reads `CLAUDE.md` and `.claude/skills/` the same way a local session would -
  no separate prompt-engineering surface to keep in sync with this repo's conventions.
- **Subscription auth, not an API key.** `claude_code_oauth_token` (from `claude setup-token`)
  bills against Pro/Max quota instead of pay-per-token API usage - this is a learning exercise,
  not a system meant to run indefinitely against metered billing.
- **Comments only, no write access to code.** `claude_args` restricts tools to
  `gh pr comment` / `gh pr diff` / `gh pr view` and the inline-comment MCP tool - the action can
  read and comment on the PR, not push commits.

## Known gaps

- Inline comment *classification* (auto-resolving low-confidence comments) requires
  `anthropic_api_key`; with only an OAuth token, comments post directly and unconfirmed ones are
  not filtered out the same way.
- No path-filtering, no separate handling for external contributors yet - every PR gets the same
  full review.
