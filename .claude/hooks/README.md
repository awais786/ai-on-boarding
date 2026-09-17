# Claude Code hooks

Two hooks, wired up in [`.claude/settings.json`](../settings.json). Both read the hook
payload as JSON on stdin, write JSON on stdout, and always exit 0 — they signal through
their output, never through an exit code.

| Hook | Event | Matcher | What it does |
|---|---|---|---|
| `protect_sensitive_files.py` | `PreToolUse` | `Read\|Write\|Edit\|MultiEdit\|NotebookEdit\|Bash` | Denies the call if it touches a protected file or carries a secret |
| `pylint_after_edit.py` | `PostToolUse` | `Write\|Edit\|MultiEdit\|NotebookEdit` | Runs Pylint on an edited Python file and feeds the report back to Claude |

## 1. `protect_sensitive_files.py` — protect sensitive files

Runs two independent checks and denies on the first hit, naming the reason.

### Protected paths, and why reading is sometimes fine

Protection comes in two flavours, because a read deserves a different answer depending on
what the file is:

| Flavour | Files | Read | Write |
|---|---|---|---|
| **Confidential** | environment files, private keys and certificates, credential stores (`.netrc`, `.npmrc`, `credentials.json`, `.aws`, `.ssh`, `.gnupg`) | refused | refused |
| **Integrity** | production settings, `.claude/settings*.json`, hook scripts, `.git/config` | allowed | refused |

Reading a confidential file is as harmful as writing one — the secret lands in the
transcript either way. For an integrity-protected file the risk is modification, not
disclosure, so linting, grepping, and reviewing it all still work. The exact glob list is
at the top of the hook source.

`Read` is matched so that the confidential row above is real: without it, `Bash("cat .env")`
was refused while `Read(".env")` was never evaluated at all, and the headline protection —
keeping a secret out of the transcript — did not apply to the most direct way of getting one.
`Read`, `NotebookRead`, `Glob` and `Grep` are classified as reads; every other tool naming a
path is treated as writing it, which is the safe default. `Glob` and `Grep` are classified but
not currently matched, so adding them to the matcher needs no further change here.

**A residual gap:** `Grep` can still surface the *contents* of a confidential file when the
path it is given is an ordinary directory that merely contains one, because only the path
argument is checked, not what the search returns. Path-based protection cannot close that;
it would need output filtering.

For `Bash`, intent is inferred from the command: redirect targets are writes, as are
arguments to a mutating command (`rm`, `mv`, `cp`, `tee`, an editor, `sed -i`, …).
Everything else counts as a read. Heredoc bodies are stripped before the scan, so a
document that merely *mentions* a protected filename is not read as an attempt to open it,
and commands that never open their arguments (`echo`, `printf`) are skipped — though their
redirect targets are still checked.

Command substitutions are lifted out and classified separately, as reads, before that
exemption is applied. Without that step the exemption swallowed the whole segment, so
`echo $(cat .env)` printed a confidential file into the transcript while a plain `cat .env`
was refused. The first word inside a substitution is checked too, because `$(<secret)` has
no command word at all.

The self-protection entries matter more than they look. `.claude/settings*.json` is a glob
rather than a single filename because *any* settings file can carry an `env` block, and an
`env` block can set this guard's own break-glass variable — so protecting only
`settings.json` left `settings.local.json` open as a way to switch the guard off. Hook
scripts are protected because Claude Code executes them on every matching tool call, which
makes writing one arbitrary code execution. Their tests, one directory down, are ordinary
source and stay editable.

### Secret-looking content

Recognisable provider credentials (Anthropic, OpenAI, GitHub, AWS, Google, Slack, GitLab,
PEM private key blocks, JWTs) anywhere in the payload, plus a generic heuristic for
hard-coded credential assignments of the `SECRET_KEY = "..."` shape.

Two carve-outs apply to the **generic heuristic only** — real provider keys stay blocked
everywhere, including in both:

- **Test files** (`test_*.py`, `*_test.py`, anything under `tests/`). Without this, every
  edit to `test_signup.py` would be blocked by its own password fixtures.
- **Prose files** (`.md`, `.rst`, `.txt`, `.adoc`). Documentation quotes credential-shaped
  examples as a matter of course; this file does.

The destination is taken from `file_path` for the path-carrying tools, and from a Bash
command's own redirect and command targets otherwise — so `cat > test_x.py <<'EOF'` earns the
same carve-out as `Write` to that path. Every destination has to qualify: a command that
writes a fixture and a source file in one go gets no exemption, and text headed nowhere in
particular gets the strict reading.

A shell command that writes nowhere is exempt from the generic heuristic too. Searching,
listing and reading are not hard-coding, and treating them alike meant `grep "SECRET = " x.py`
was refused for carrying the string it was sent to find — as was any script quoting a line of
this guard's own source. Exporting is exempt for the same reason, and because putting a
credential in the environment is what the block message recommends.

The exception is a command that sends data off the machine (`curl`, `wget`, `ssh`, `scp`,
`rsync`, `mail`, `nc` and friends): nothing is written, but the text still leaves, so the
heuristic applies. Provider keys are matched everywhere regardless, so a real key cannot ride
out on any of these.

Placeholder values (`<your-key-here>`, `changeme`, `${VAR}`, `os.environ[...]`) are never
treated as secrets.

### Break glass

Set `CLAUDE_HOOKS_ALLOW_PROTECTED=1` in the environment Claude Code runs in to downgrade
every block to a warning:

```sh
CLAUDE_HOOKS_ALLOW_PROTECTED=1 claude --continue
```

This exists because the guard protects its own source: without an override, a mistake in it
could only be corrected outside Claude Code. It must be set for the *Claude Code process* —
setting it inside a Bash tool call does not reach the hook, so it cannot be switched on
mid-session. Launch without it and the guard is back at full strength.

The test suite clears this variable in an autouse fixture, so the tests mean the same thing
whether or not the session that runs them has the override on.

### Failure behaviour

If the guard raises while evaluating a call, it **denies** rather than allowing. A security
control that fails open is not a control.

## 2. `pylint_after_edit.py` — lint Python after edits

Detects the edited file from `tool_response.filePath`, falling back to
`tool_input.file_path`. Non-Python files produce no output at all and Pylint is never
invoked for them. For a Python file that exists on disk, Pylint runs and any report comes
back to Claude as `hookSpecificOutput.additionalContext`, so it can act on the findings.

Pylint is located in this order: `$PYLINT`, then `.venv/bin/pylint` beside the project,
then `pylint` on `PATH`, then `python -m pylint`. If none resolve, the hook says so once as
a user-visible note instead of failing the edit. Timeouts and Pylint usage errors are
reported the same way, and are never fed back as if they were lint findings.

Message selection is governed by [`.pylintrc`](../../.pylintrc) at the repository root,
which disables the messages that fire on correct Django/DRF code (`too-few-public-methods`
on `Meta` classes, `unused-argument` on `request`) and the docstring messages this project
does not follow. Pylint also needs the project's own dependencies importable, or every
Django import is reported as `E0401`. Without both of those, the hook reports mostly noise:
on `api/serializers.py` it drops from 14 messages to 2.

## Running the tests

The hooks depend only on the standard library; the tests need `pytest`, and the Pylint
tests need `pylint`:

```sh
python3 -m venv .venv
.venv/bin/pip install -r .claude/hooks/requirements-dev.txt
.venv/bin/pytest .claude/hooks
```

Tests that need Pylint skip themselves if it is not installed, so the suite still passes in
a bare environment.
