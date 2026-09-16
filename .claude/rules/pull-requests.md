# Creating pull requests

These rules apply to every PR opened for this repo, without needing to be separately invoked.

- **Every PR must reference the GitHub issue it addresses.** Find it, in order, from: the branch
  name, commit messages (`Closes #N`, `Fixes #N`, a plain `#N`), the linked OpenSpec change's
  issue, or conversation context. If none of these give a confident match, stop and ask the user
  which issue it is — never guess an issue number or open a PR with no issue link. Confirm with
  the user whether to use `Closes #N` or `Relates to #N`, unless they've already stated it.
- **Keep each PR scoped to one issue.** If the working tree has changes for more than one
  unrelated piece of work, split them into separate branches/PRs rather than bundling them —
  don't fold an unrelated fix or file into a PR just because it happened to be sitting in the
  working tree.
- **`/code-review` must return `Ready to merge: yes` before the PR is opened** (the review contract
  in `CLAUDE.md`). Ask the user whether review has already passed; don't run `/code-review`
  yourself without asking first, since it has a real token cost the user controls. If they
  decline review and still want to proceed, don't silently open it anyway — either an explicit
  `gh pr create --draft` (openly unreviewed) or stop.
- `pytest` should pass for the whole project before opening the PR, not just before archiving.
- Keep PR descriptions lean: a short "what changed" summary plus the issue reference — no
  exhaustive changelog.
- This repo's upstream is `awais786/ai-on-boarding`; work happens on a fork (`origin`), and PRs
  are opened from a fork branch against `upstream:main` — confirm the remote names in
  `git remote -v` rather than assuming, since fork setups vary per contributor.
