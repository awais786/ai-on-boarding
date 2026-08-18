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

### 2. Create your repository

```bash
mkdir sdd-django-demo && cd sdd-django-demo
git init
```

Leave it empty. You are not going to create the Django project by hand — that is phase 1's job,
and doing it by hand would contradict everything this exercise teaches.

### 3. Install Spec Kit into the project

Spec Kit is GitHub's open-source toolkit for spec-driven development. It adds a set of slash
commands to Claude Code that walk a feature from idea to implementation.

```bash
uvx --from git+https://github.com/github/spec-kit.git specify init . --ai claude
```

If you do not have `uv`, install it first — see the [Spec Kit
README](https://github.com/github/spec-kit).

The `--ai claude` flag matters. It writes the command definitions into `.claude/commands/`
so Claude Code can find them.

### 4. Verify the commands exist — do not skip this

Start Claude Code in the project:

```bash
claude
```

Then type `/help` and look for commands beginning with `speckit`. You should see roughly:

```
/speckit.constitution
/speckit.specify
/speckit.clarify
/speckit.plan
/speckit.tasks
/speckit.implement
```

There may be others (`analyze`, `checklist`, `taskstoissues`). You will not use those.

*Verified against Spec Kit on 18 August 2026. Command names move — if the list differs but the
same six ideas are present, use the names your `/help` shows.*

### 5. Commit

```bash
git add .
git commit -m "Initialise Spec Kit"
```

## Done when

- [ ] `claude --version` prints a version
- [ ] You are inside a git repository named `sdd-django-demo`
- [ ] `/help` inside Claude Code lists the `speckit` commands
- [ ] You have one commit

## If it goes wrong

**The `speckit` commands do not appear in `/help`.** This is the most common failure, and it is
known — Claude Code sometimes does not pick up newly written command files mid-session.

1. Quit Claude Code entirely (`/exit`) and start it again. This fixes it most of the time.
2. Check the files exist: `ls .claude/commands/`. If that directory is empty or missing, the
   `specify init` did not complete — re-run step 3 and read its output for errors.
3. Confirm you passed `--ai claude`. Without it, Spec Kit writes commands for a different agent
   and Claude Code will never see them.
4. Still nothing? You can complete this entire exercise without the slash commands by opening
   the corresponding file in `.specify/templates/` and asking Claude to follow it. It is
   clumsier, but nothing here depends on the commands specifically — they are a convenience
   over prompts.

**`uvx` is not found.** Install `uv` (see the Spec Kit README), or use `pipx` as an alternative
runner.
