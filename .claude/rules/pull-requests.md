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
- **Link `traceability.md` instead of repeating it.** For a change built through OpenSpec, the
  requirement→code→test mapping already lives in `openspec/changes/<name>/traceability.md` (built
  per `openspec/config.yaml`'s `operations.apply.guidance`). Link it from the PR description
  rather than re-listing requirements inline — that keeps the description lean without losing
  traceability.
- **Give the exact verification command(s)**, not just "tests pass" — e.g. `pytest` or a specific
  `pytest path/to/test_file.py`. A reviewer should not have to work out how to run this.
- **Name one open uncertainty.** Per `starter/pull_request_template.md`'s "What I am unsure
  about" section: name at least one arbitrary decision, ambiguous requirement, or test you don't
  fully trust. A PR claiming total confidence gets a shallower review than one that points at its
  own weak spot.
- Keep PR descriptions lean: a short "what changed" summary, the issue reference, the
  traceability/verification links, and the one uncertainty above — nothing more, no exhaustive
  changelog.
- **Sync with upstream `main` before opening the PR.** Merge or rebase the latest `upstream/main`
  into the branch first, so the PR doesn't open stale or with avoidable conflicts.
- This repo's upstream is `awais786/ai-on-boarding`; work happens on a fork (`origin`), and PRs
  are opened from a fork branch against `upstream:main` — confirm the remote names in
  `git remote -v` rather than assuming, since fork setups vary per contributor.
