# Phase 1 — Build the scaffold

## What you'll do

Get a working Django + DRF + pytest project, built by Claude Code from a specification you hand
it. You will not type any Django code.

This is the exercise in miniature: **specify → implement → verify**, before Spec Kit's larger
ceremony arrives. If you have never used Django, that is fine. You are not learning Django here.
You are learning to describe what you want and check what you got.

## Time

About 1 hour.

## Before you start

Phase 0 complete: a git repo with Spec Kit initialised, and the `speckit` commands visible
in `/help`.

## Steps

### 1. Read the specification you are about to use

Open [`starter/scaffold-spec.md`](../starter/scaffold-spec.md) and read it properly —
five minutes, not a skim.

Notice its shape. It states required *names*, required *behaviour*, and what is explicitly out
of scope. It does not say which files to create, what the model layer looks like, or how to wire
the URL. That is the line between what and how, and you will be walking it for the rest of the
exercise.

### 2. Hand it to Claude Code

From your project directory:

```bash
claude
```

Then:

```
Read starter/scaffold-spec.md and build exactly what it specifies.
Do not add anything it puts out of scope. When you are done, tell me which
of its acceptance checks you ran and what each one printed.
```

If the scaffold spec is not inside your project, paste its contents instead.

### 3. Watch what it does

Do not walk away. Read the files as they appear. You will not understand every line, and you do
not need to — but you should be able to answer, roughly, "what is this file for?" Ask Claude
directly when you cannot:

```
What is settings.py for, in one paragraph?
```

Getting comfortable asking that question is worth more than the answer.

### 4. Run the acceptance checks yourself

Claude will tell you the checks passed. Believe it after you have seen it, not before.

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate
.venv/bin/pytest
```

Then start the server and hit the endpoint:

```bash
.venv/bin/python manage.py runserver
```

In another terminal:

```bash
curl -i http://127.0.0.1:8000/api/health/
```

You want `HTTP/1.1 200 OK` and `{"status": "ok"}`.

Then open **http://127.0.0.1:8000/api/docs/** in a browser. You should get Swagger UI — an
interactive page listing your endpoints, with a **Try it out** button on each.

This is worth more to you than curl. For the rest of the exercise it is how you will poke at the
API by hand, and in phase 5 it becomes a verification instrument in its own right.

### 5. Install the Django skill

A **skill** is a folder of instructions Claude loads by itself when the work matches. You are
about to install one describing how this project does Django — layout, migration policy, auth
rules, test conventions — so that generated code follows them without you repeating yourself
every session.

```bash
mkdir -p .claude/skills
cp -r ../ai-on-boarding/starter/skills/django-conventions .claude/skills/
```

Adjust the source path to wherever this course repo lives.

Verify Claude can see it — in a fresh Claude Code session:

```
Which skills are available in this project?
```

`django-conventions` should be listed. Then check it actually applies:

```
How should I add a new endpoint to this project, and how are migrations handled here?
```

The answer should match the skill — serializer first, thin views, generated migrations that are
never hand-edited. If it gives you generic Django advice instead, the skill is not loading; see
*If it goes wrong*.

Read `SKILL.md` yourself too. It is short, and you will be extending it later.

### 6. Add the pull request template

Your work will be reviewed by a lead, through pull requests. GitHub fills every new PR from a
template, so put one in place now:

```bash
mkdir -p .github
cp ../ai-on-boarding/starter/pull_request_template.md .github/
```

Open it and read the sections. Two are worth noticing before you ever use it: **The plan**, which
is what a reviewer judges before opening the diff, and **What I am unsure about**, which is
required. A pull request that claims total confidence gets a shallower review than one that
points at its own weak spot.

### 7. Commit

```bash
git add .
git commit -m "Add Django + DRF + pytest scaffold, project skill and PR template"
git push
```

Push this one. The scaffold is shared starting ground, not part of any feature, so it belongs on
`main` before you branch in phase 2. Leave it unpushed and your first pull request will show the
whole scaffold sitting on top of your specification, which buries the thing your lead is meant to
be reading.

## Done when

- [ ] `manage.py check` reports no issues
- [ ] `pytest` reports **1 passed**
- [ ] `curl http://127.0.0.1:8000/api/health/` returns `{"status": "ok"}` with status 200
- [ ] `http://127.0.0.1:8000/api/docs/` renders Swagger UI and lists the health endpoint
- [ ] `http://127.0.0.1:8000/api/schema/` returns an OpenAPI document
- [ ] `requirements.txt` pins exact versions, with a date comment
- [ ] `.github/pull_request_template.md` exists
- [ ] `.claude/skills/django-conventions/SKILL.md` exists and Claude lists it
- [ ] Asking how to add an endpoint gives you *this project's* answer, not generic Django advice
- [ ] There is **no** signup, login, or authentication code anywhere yet
- [ ] You did not hand-write any Django code to get here
- [ ] Your commit is pushed — `main` on GitHub shows the scaffold
- [ ] Your commit is in

That last-but-one box matters. If Claude helpfully added a user model or a login view, delete
it. Those are built later, through the workflow — and building them now removes the exercise.

## If it goes wrong

**`pytest` reports "no tests ran".** Two causes, and the second is easy to miss.

Either `DJANGO_SETTINGS_MODULE` is not configured for pytest — ask Claude: *"pytest cannot find
the Django settings — fix the pytest configuration so `pytest` runs from the project root."*

Or the test file is named `api/tests.py`. That is the name `django-admin startapp` generates, and
pytest does not collect it: the default pattern is `test_*.py`. Rename it to `api/test_health.py`.

**Do not read "no tests ran" as a pass.** pytest exits without complaint and prints no failures,
so a quick glance says everything is fine while nothing whatsoever was verified. This is why the
checklist asks for **1 passed** rather than "pytest passes" — and it is the same trap, in
miniature, as a test suite that goes green because its assertions never execute.

**`/api/docs/` returns 500 with `TemplateDoesNotExist: drf_spectacular/swagger_ui.html`.** The
package is installed but missing from `INSTALLED_APPS`, so Django never looks in its template
directory. Ask Claude: *"`/api/docs/` raises TemplateDoesNotExist. Check that `drf_spectacular`
and `rest_framework` are in INSTALLED_APPS."*

This one is worth dwelling on, because **`manage.py check` and `pytest` will both pass while it is
broken.** A DRF view and a URL route work whether or not the apps are installed. If you had
trusted the green suite and skipped the endpoint checks, you would have carried a misconfigured
project into every later phase. That is the whole argument for the *Done when* lists.

**Swagger UI is blank, or `/api/docs/` 404s.** The docs URL is not routed. Ask Claude to show you
`api/urls.py` and confirm the schema and docs paths are registered.

**The health endpoint 404s.** The URL is not wired into the project's root URL configuration.
Ask Claude to show you `sdd_django_demo/urls.py` and explain how a request reaches the health
view — then have it fix the wiring.

**Claude built more than the spec asked for.** Say so plainly: *"The scaffold spec puts
authentication out of scope. Remove everything it did not ask for."* Then re-run the checks.
This happens often, and noticing it is a real skill — it is the same skill phase 3 is about.

**Claude does not list the skill, or ignores it.** Confirm the file is at exactly
`.claude/skills/django-conventions/SKILL.md` — the folder name and the `name:` in its frontmatter
must match. Then restart Claude Code; skills are discovered at session start, so one added
mid-session will not appear. If it is listed but not applied, the task may not look relevant to
it — mention Django explicitly in your request.

**Something is broken and you cannot tell what.** Paste the exact error into Claude and ask for
the cause before the fix: *"What is causing this? Do not change anything yet."* Understanding
first, then fixing, is a habit worth building now.
