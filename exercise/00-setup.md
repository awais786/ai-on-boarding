# Phase 0 — Setup

## What you'll do

Install Claude Code and GitHub Spec Kit, create your project repository, and prove the Spec Kit
commands actually work before you depend on them.

## Time

About 45 minutes.

## Before you start

- Python 3.12+ (`python3 --version`)
- Git, and a GitHub account
- A terminal

## Steps

### 1. Install Claude Code

Follow the [official install guide](https://docs.claude.com/en/docs/claude-code). Then check it:

```bash
claude --version
```

Deliberately not pasted here: the install command changes, and a stale command in a tutorial
is worse than a link. The docs are the source of truth.

### 2. Create your repository — on GitHub, not just locally

Your lead reviews your work through pull requests, so the repository has to be somewhere they can
see it.

With the GitHub CLI:

```bash
gh repo create sdd-django-demo --private --clone
cd sdd-django-demo
```

Without it — create an empty private repository named `sdd-django-demo` on github.com, then:

```bash
mkdir sdd-django-demo && cd sdd-django-demo
git init
git remote add origin git@github.com:<your-username>/sdd-django-demo.git
```

**Send your lead the URL and check they have access.** They cannot review what they cannot see,
and you will be blocked at phase 3 otherwise.

Leave the repository empty otherwise. You are not going to create the Django project by hand —
that is phase 1's job, and doing it by hand would contradict everything this exercise teaches.

### 3. Install Spec Kit into the project

Spec Kit is GitHub's open-source toolkit for spec-driven development. It installs a set of
skills into Claude Code that walk a feature from idea to implementation.

```bash
uvx --from git+https://github.com/github/spec-kit.git specify init . --integration claude
```

If you do not have `uv`, install it first — see the [Spec Kit
README](https://github.com/github/spec-kit).

The `--integration claude` flag matters. It writes the skill definitions into `.claude/skills/`
so Claude Code can find them. Without it Spec Kit sets up for a different agent and none of the
commands below will appear.

Spec Kit will warn that the directory is not empty — that is the `.git` folder you just created,
and it is expected. Confirm the merge when it asks.

### 4. Verify the commands exist — do not skip this

Start Claude Code in the project:

```bash
claude
```

Then type `/help` and look for commands beginning with `speckit`. You should see roughly:

```
/speckit-constitution
/speckit-specify
/speckit-clarify
/speckit-plan
/speckit-tasks
/speckit-implement
```

There may be others (`analyze`, `checklist`, `converge`, `taskstoissues`). You will not use those.

*Verified against Spec Kit on 19 August 2026. These names move — they were dotted
(`/speckit.specify`) in earlier releases and may change again. If the list differs but the same
six ideas are present, use the names your own `/help` shows.*

### 5. Commit and push

```bash
git add .
git commit -m "Initialise Spec Kit"
git push -u origin main
```

**Push, do not just commit.** Your lead reviews pull requests, and a pull request needs a base
branch on GitHub to compare against. If `main` has never been pushed, the first branch you push
becomes the default and there is nothing to open a pull request against — you will reach phase 3
and find GitHub offers you no way to create one.

If your branch is called `master`, push that instead and use it wherever these instructions say
`main`.

## Done when

- [ ] `claude --version` prints a version
- [ ] You are inside a git repository named `sdd-django-demo`
- [ ] `git remote -v` shows an `origin` pointing at your GitHub repository
- [ ] Your lead has the URL and can see it
- [ ] `/help` inside Claude Code lists the `speckit` commands
- [ ] You have one commit, and `git push` has run
- [ ] `main` appears on GitHub when you open the repository in a browser

## If it goes wrong

**The `speckit` commands do not appear in `/help`.** This is the most common failure, and it is
known — Claude Code sometimes does not pick up newly written command files mid-session.

1. Quit Claude Code entirely (`/exit`) and start it again. This fixes it most of the time.
2. Check the files exist: `ls .claude/skills/`. You should see one directory per command, each
   holding a `SKILL.md`. If it is empty or missing, `specify init` did not complete — re-run
   step 3 and read its output for errors.
3. Confirm you passed `--integration claude`. Without it, Spec Kit sets up for a different agent
   and Claude Code will never see the skills.
4. Still nothing? You can complete this entire exercise without the slash commands by opening
   the corresponding file in `.specify/templates/` and asking Claude to follow it. It is
   clumsier, but nothing here depends on the commands specifically — they are a convenience
   over prompts.

**`gh repo create` says "Resource not accessible by personal access token".** Your GitHub
token is a fine-grained one without repository-creation rights. Use the manual path in step 2 —
create the repository in the browser, then add the remote by hand. The same limitation will stop
`gh pr create` at phase 3, so open pull requests in the browser too.

**`git push` later says "'origin' does not appear to be a git repository".** You created the
repository locally but never linked it to GitHub. Go back to step 2 and add the remote.

**`specify init .` complains about the directory or the argument.** Some versions want a project
name rather than a dot. If the dot form is rejected, run it from the parent directory with the
folder name — `specify init sdd-django-demo --integration claude` — and check the result landed
inside your repository, not beside it.

**`specify init` rejects `--ai`.** That flag was renamed to `--integration`. Run
`specify init --help` to see the options your version actually takes.

**`uvx` is not found.** Install `uv` (see the Spec Kit README), or use `pipx` as an alternative
runner.
