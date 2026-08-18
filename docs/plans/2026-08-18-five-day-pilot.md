# Five-Day Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working Django seed, a judgement set, and Modules 0–3 so real freshers can start the course on day 6.

**Architecture:** A minimal Django sign-in skeleton carrying deliberate, documented defects is the substrate every exercise runs against. Modules are standalone markdown; there is no runner in the pilot. The judgement set is a set of patches against the seed, each with a reproducible failure recorded in an answer key.

**Tech Stack:** Python 3.12+, Django (current stable, pinned at Task 2), SQLite, Django's built-in test runner. Content is GitHub-flavoured Markdown.

**Spec:** `docs/specs/2026-08-18-agentic-coding-onboarding-design.md`

## Global Constraints

- **Claude Code only for the pilot.** Cursor and Copilot columns in every mechanics table read `not yet verified` — never a guess.
- **No runner skill.** Modules must read correctly standalone. Do not create `runner-prompt.md` or `skills/`.
- **No reference solutions, no Tier 2 tables.** Deferred past the pilot.
- **Volatile facts are sourced at build time**, never from memory: model IDs, limits, pricing, command names, file conventions. Record the verification date in the file that carries the fact.
- **Every module file has the eight sections** from the spec's *Module structure*, in order: Objective, The failure this prevents, Concepts, Mechanics by tool, Walkthrough, Exercise, Verification criteria, Common mistakes.
- **The seed's warts are intentional and documented.** Never "fix" them outside the module that targets them.
- **Modules 4–7 are out of scope for these five days.** They are built during the cohort's first two weeks.
- Commit after every task. Work on branch `pilot/five-day-build`.

---

## File Structure

```
LICENSE                                   Task 1
.gitignore                                Task 1
README.md                                 rewritten Task 9
docs/specs/...-design.md                  banner added Task 1
seed/
  README.md                               Task 3  (documents the warts)
  requirements.txt                        Task 2
  manage.py                               Task 2
  signin/{__init__,settings,urls,wsgi}.py Task 2
  accounts/{__init__,apps,models,views,urls}.py  Task 2, warts Task 3
  accounts/tests/{__init__,test_views}.py Task 2, Task 3
judgement-set/
  README.md                               Task 4  (learner-facing)
  ANSWER-KEY.md                           Task 4  (do not read before attempting)
  patches/01..06.patch                    Task 4
modules/
  00-first-session/{shared,claude-code}.md  Task 5
  01-judging-output.md                    Task 6
  02-working-agreement.md                 Task 7
  03-context-management.md                Task 8
progress-template.md                      Task 9
```

---

### Task 1: Repo hygiene and honesty

**Files:**
- Create: `LICENSE`, `.gitignore`
- Modify: `docs/specs/2026-08-18-agentic-coding-onboarding-design.md` (add banner after line 5)

**Interfaces:**
- Consumes: nothing.
- Produces: a repo that can legally be cloned and shared; a spec that identifies itself as a builder document.

- [ ] **Step 1: Create the branch**

```bash
cd /Users/awais.qureshi/Documents/devstack/ai-on-boarding
git checkout -b pilot/five-day-build
```

- [ ] **Step 2: Add MIT LICENSE**

Write `LICENSE` with the standard MIT text, `Copyright (c) 2026 Awais Qureshi`.

- [ ] **Step 3: Add .gitignore**

```gitignore
__pycache__/
*.py[cod]
.venv/
venv/
db.sqlite3
.DS_Store
.idea/
*.egg-info/
```

- [ ] **Step 4: Mark the spec as a builder document**

Insert immediately after the `**Status:**` line:

```markdown
> **This is a design document for whoever builds the course, not a learner document.**
> If you are here to take the course, start at [`README.md`](../../README.md).
```

- [ ] **Step 5: Commit**

```bash
git add LICENSE .gitignore docs/specs/
git commit -m "Add licence, gitignore, and a builder-document banner on the spec"
```

---

### Task 2: Django seed, green on a clean checkout

**Files:**
- Create: `seed/requirements.txt`, `seed/manage.py`, `seed/signin/__init__.py`, `seed/signin/settings.py`, `seed/signin/urls.py`, `seed/signin/wsgi.py`, `seed/accounts/__init__.py`, `seed/accounts/apps.py`, `seed/accounts/models.py`, `seed/accounts/views.py`, `seed/accounts/urls.py`
- Test: `seed/accounts/tests/__init__.py`, `seed/accounts/tests/test_views.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Profile(user, display_name)`; views `home(request)` and `dashboard(request)`; URLs `/` and `/dashboard/`; test command `python manage.py test`.

- [ ] **Step 1: Determine and pin the current stable Django**

Do not guess the version. Run:

```bash
python3 -m pip index versions django
```

Take the highest stable release. Record it and today's date in `seed/requirements.txt`:

```
# Verified against PyPI on 2026-08-18
Django==<VERSION FROM THE COMMAND ABOVE>
```

- [ ] **Step 2: Create the virtualenv and install**

```bash
cd seed && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

- [ ] **Step 3: Write `seed/signin/settings.py`**

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-course-seed-do-not-use-in-production"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "signin.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "signin.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

- [ ] **Step 4: Write the remaining project files**

`seed/manage.py`:

```python
#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "signin.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

`seed/signin/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
]
```

`seed/signin/wsgi.py`:

```python
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "signin.settings")
application = get_wsgi_application()
```

`seed/signin/__init__.py`, `seed/accounts/__init__.py`, `seed/accounts/tests/__init__.py`: empty files.

`seed/accounts/apps.py`:

```python
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
```

`seed/accounts/models.py`:

```python
from django.conf import settings
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.display_name or self.user.username
```

`seed/accounts/urls.py`:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
```

`seed/accounts/views.py` (the plain version; Task 3 introduces the warts):

```python
from django.http import HttpResponse

from .models import Profile


def home(request):
    return HttpResponse("signin seed")


def dashboard(request):
    profile = Profile.objects.get(user=request.user)
    return HttpResponse(f"Hello, {profile.display_name or request.user.username}")
```

- [ ] **Step 5: Write the failing test**

`seed/accounts/tests/test_views.py`:

```python
from django.contrib.auth.models import User
from django.test import TestCase

from accounts.models import Profile


class HomeTests(TestCase):
    def test_home_responds(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)


class DashboardTests(TestCase):
    def test_greets_logged_in_user_by_display_name(self):
        user = User.objects.create_user("ada", password="pw")
        Profile.objects.create(user=user, display_name="Ada")
        self.client.force_login(user)

        response = self.client.get("/dashboard/")

        self.assertContains(response, "Ada")
```

- [ ] **Step 6: Run the tests and make migrations**

```bash
cd seed && .venv/bin/python manage.py makemigrations accounts && .venv/bin/python manage.py test
```

Expected: 2 tests pass. If `makemigrations` reports no changes, the app is not in `INSTALLED_APPS` — fix that first.

- [ ] **Step 7: Verify green on a clean checkout**

This is the step that matters. In a scratch directory:

Commit first — the clone only sees committed work. Do **not** stash; it risks losing uncommitted
work and is unnecessary here.

```bash
cd /Users/awais.qureshi/Documents/devstack/ai-on-boarding
git status --short          # expect clean, or commit before continuing
cd /tmp && rm -rf seedcheck
git clone /Users/awais.qureshi/Documents/devstack/ai-on-boarding seedcheck
cd seedcheck/seed && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py test
```

Expected: 2 tests pass. A failure here means a file was never committed — add it and repeat.

- [ ] **Step 8: Commit**

```bash
cd /Users/awais.qureshi/Documents/devstack/ai-on-boarding
git add seed/
git commit -m "Add Django sign-in seed: Profile, home and dashboard views, passing tests"
```

---

### Task 3: The seed's deliberate warts

**Files:**
- Modify: `seed/accounts/views.py`
- Create: `seed/README.md`

**Interfaces:**
- Consumes: `Profile`, `dashboard` from Task 2.
- Produces: a documented crash on the anonymous-user path of `/dashboard/`, which is Module 0's exercise, and an over-stuffed view that is Module 3's refactoring target.

- [ ] **Step 1: Replace `dashboard` with the over-stuffed version**

Wart 1 is that this view does four things. Wart 2 is that the anonymous branch is untested and crashes.

```python
from django.http import HttpResponse

from .models import Profile


def home(request):
    return HttpResponse("signin seed")


def dashboard(request):
    profile = Profile.objects.get(user=request.user)

    name = profile.display_name or request.user.username

    if request.GET.get("format") == "short":
        body = name
    else:
        body = f"Hello, {name}. You have no messages."

    return HttpResponse(body)
```

- [ ] **Step 2: Confirm the anonymous path really is broken**

```bash
cd seed && .venv/bin/python manage.py shell -c "
from django.test import Client
print(Client().get('/dashboard/'))
"
```

Expected: raises — `Profile.objects.get(user=AnonymousUser)` cannot resolve. Record the exact exception type; Module 0 and the answer key both cite it.

- [ ] **Step 3: Confirm the existing tests still pass**

```bash
cd seed && .venv/bin/python manage.py test
```

Expected: 2 pass. The crash is invisible to the suite — that is the point.

- [ ] **Step 4: Document the warts as intentional**

`seed/README.md`:

```markdown
# signin — course seed

A deliberately small Django project. You build the authentication features on top of it as you
work through the course: sign-up, log-in, password reset, and the capstone feature.

## Running it

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python manage.py migrate
    .venv/bin/python manage.py test

## Intentional defects — do not "fix" these early

This seed ships with known problems. They are teaching material, and each one is the target of a
specific module. Fixing them ahead of time removes the exercise.

1. **`dashboard` does too much.** One view resolves a profile, derives a display name, branches on a
   query parameter and renders. Module 3 uses it.
2. **The anonymous-user path of `/dashboard/` crashes, and no test covers it.** The suite is green
   and the code is broken — which is exactly the gap Module 0 asks you to close.

If you find a third problem, that is a legitimate finding. Write it down; you will need it in
Module 6.
```

- [ ] **Step 5: Commit**

```bash
git add seed/
git commit -m "Add the seed's intentional warts and document them"
```

---

### Task 4: The judgement set

**Files:**
- Create: `judgement-set/README.md`, `judgement-set/ANSWER-KEY.md`, `judgement-set/patches/01.patch` … `06.patch`

**Interfaces:**
- Consumes: the seed at the commit from Task 3.
- Produces: six patches — three sound, three defective — each defective one with a named, reproducible failure. Module 1 grades against `ANSWER-KEY.md`.

- [ ] **Step 1: Generate each patch from a real commit**

For each of the six changes below, make the change on a scratch branch, commit it, and export it:

```bash
git checkout -b scratch/patch-01 && <make change> && git commit -am "patch 01"
git format-patch -1 --stdout > judgement-set/patches/01.patch
git checkout pilot/five-day-build && git branch -D scratch/patch-01
```

The six:

| # | Change | Sound? |
|---|---|---|
| 01 | Adds `/healthz/` returning 200 `"ok"`, with a test | ✅ |
| 02 | Adds `greeting_for(user)` returning `user.profile.display_name or user.username` | ❌ crashes for a user with no Profile |
| 03 | Adds a test covering the anonymous `/dashboard/` path | ✅ |
| 04 | Adds `page_slice(items, page, size)` using `items[page * size:(page + 1) * size]`, documented as 1-indexed | ❌ off-by-one: page 1 skips the first `size` items |
| 05 | Adds `email_is_registered(email)` view returning 200 when known, 404 when not | ❌ account enumeration |
| 06 | Extracts `_display_name(profile, user)` from `dashboard`, no behaviour change, tests still pass | ✅ |

- [ ] **Step 2: Verify every patch applies cleanly**

```bash
for p in judgement-set/patches/*.patch; do
  git apply --check "$p" && echo "OK   $p" || echo "FAIL $p"
done
```

Expected: six `OK` lines. A patch that does not apply is worthless to a learner.

- [ ] **Step 3: Verify each defect actually reproduces**

For 02, 04 and 05, apply the patch, run the reproduction, confirm the failure, then reset:

```bash
git apply judgement-set/patches/02.patch
cd seed && .venv/bin/python manage.py shell -c "
from django.contrib.auth.models import User
from accounts.views import greeting_for
u = User.objects.create_user('bob', password='pw')   # no Profile
print(greeting_for(u))
"
cd .. && git checkout -- seed/
```

Expected: raises `Profile.DoesNotExist` (or `RelatedObjectDoesNotExist`). Record the exact exception. Repeat for 04 (assert page 1 returns the first `size` items and observe it does not) and 05 (two requests, one known and one unknown email, showing the responses differ).

**A patch whose defect you cannot reproduce does not belong in the set.** Replace it.

- [ ] **Step 4: Write the learner-facing README**

`judgement-set/README.md`:

```markdown
# Judgement set

Six changes to the seed. Some are sound. Some are not.

For each one, decide **accept** or **reject**, and write down the evidence that took you there — a
test you ran, an input you traced, a criterion you can point at.

    git apply --check judgement-set/patches/01.patch    # does it apply?
    git apply judgement-set/patches/01.patch            # try it
    git checkout -- seed/                               # undo

A correct verdict backed by a hunch scores as a miss. The evidence is the skill.

Do not open `ANSWER-KEY.md` until you have written all six verdicts down.
```

- [ ] **Step 5: Write the answer key**

`judgement-set/ANSWER-KEY.md` — one section per patch: verdict, the defect in one sentence, the exact reproduction command, and the expected output. Use the exact exception names recorded in Step 3, not paraphrases.

- [ ] **Step 6: Commit**

```bash
git add judgement-set/
git commit -m "Add judgement set: six patches, three defective, each with a reproducible failure"
```

---

### Task 5: Module 0 — First session: asking and running

**Files:**
- Create: `modules/00-first-session/shared.md`, `modules/00-first-session/claude-code.md`

**Interfaces:**
- Consumes: the seed (Tasks 2–3).
- Produces: the learner's first commit and their working copy of the seed.

- [ ] **Step 1: Verify the command surface before writing it down**

Do not write command names from memory. In Claude Code, run `/help` and record what is actually there. Note the date. Anything you cannot confirm does not go in the module.

- [ ] **Step 2: Write `shared.md`**

Eight sections in the spec's order. Content per the spec's Module 0: the loop, reviewing a diff before accepting, permission modes, when to stop the agent, and **asking for work** — scope tightly, point at an existing pattern rather than describing a convention, give it a check it can run, describe a bug by symptom/location/definition-of-fixed, and Explore → Plan → Implement → Commit.

The **Mechanics by tool** table must read:

| Technique | Claude Code | Cursor | Copilot |
|---|---|---|---|
| … | `<verified command>` | not yet verified | not yet verified |

- [ ] **Step 3: Write `claude-code.md`**

Install, authentication, opening the project, and the verified command surface from Step 1 with the verification date stated in the file.

- [ ] **Step 4: Write the exercise and verification criteria**

Exercise: get the seed green, then fix the crashing anonymous `/dashboard/` path **twice** — once from a vague one-line request, once from a scoped request naming the file, the expected behaviour and the test. Review both diffs, keep the better one, commit it.

Verification: tests pass and now include an anonymous-path test; a commit exists; the learner can state what changed, why they accepted it, and one concrete difference between what the two prompts produced.

- [ ] **Step 5: Commit**

```bash
git add modules/00-first-session/
git commit -m "Add Module 0: first session, asking and running"
```

---

### Task 6: Module 1 — Judging output you didn't write

**Files:**
- Create: `modules/01-judging-output.md`

**Interfaces:**
- Consumes: `judgement-set/` (Task 4).
- Produces: the learner's six written verdicts with evidence.

- [ ] **Step 1: Write the module**

Eight sections. Concepts: reading a diff for what it does rather than what the summary claims; running the tests before believing the claim; reproducing before accepting a fix; plausible-but-wrong; when to stop the agent.

- [ ] **Step 2: Write the exercise and verification**

Exercise: work all six patches, one verdict and one piece of evidence each, before opening the answer key.

Verification: verdicts match the key **and** every rejection cites reproducible evidence. State explicitly that a correct verdict reached by hunch scores as a miss.

- [ ] **Step 3: Self-check against the answer key**

Work the six patches yourself as a learner would, using only `judgement-set/README.md`. If any defect is not findable from the patch alone in under ten minutes, the patch is too subtle — fix Task 4's patch rather than weakening this module.

- [ ] **Step 4: Commit**

```bash
git add modules/01-judging-output.md
git commit -m "Add Module 1: judging output you didn't write"
```

---

### Task 7: Module 2 — Working agreement

**Files:**
- Create: `modules/02-working-agreement.md`

**Interfaces:**
- Consumes: the learner's seed copy.
- Produces: an `AGENTS.md` in the learner's working copy.

- [ ] **Step 1: Re-verify the AGENTS.md / CLAUDE.md split**

The spec names this the highest-churn fact in the course. Check whether Claude Code has shipped native `AGENTS.md` support. Record the date and the answer in the module.

- [ ] **Step 2: Write the module**

Eight sections. Concepts per the spec: what belongs in an instructions file and what does not; `AGENTS.md` as the standard with Claude Code as the named exception and the `CLAUDE.md`-points-at-`AGENTS.md` bridge; **the token tax** — everything always-on is re-paid every request, which is why both tools cap their always-on surface by convention; and the four-way table for instructions file vs skill vs slash command vs subagent vs hook, with authoring explicitly out of scope.

- [ ] **Step 3: Write the exercise and verification**

Exercise: write `AGENTS.md` for the seed covering at minimum the test command, the migration policy (generated, never hand-edited), where settings live, and the intentional warts that must not be "fixed". Wire it up for Claude Code. Run one task with and without it.

Verification: the file contains project-specific, checkable instructions rather than generic advice; the tool demonstrably reads it; the learner can name the observed difference.

- [ ] **Step 4: Commit**

```bash
git add modules/02-working-agreement.md
git commit -m "Add Module 2: working agreement, the token tax, and the mechanism table"
```

---

### Task 8: Module 3 — Context management

**Files:**
- Create: `modules/03-context-management.md`

**Interfaces:**
- Consumes: the seed and the learner's `AGENTS.md`.
- Produces: working sign-up and log-in with tests in the learner's copy.

- [ ] **Step 1: Run the exercise yourself first**

Implement sign-up and log-in against the seed with no context discipline. Record what actually filled the context and at what point quality dropped. **The module is written from this observation, not from theory** — if it does not sprawl, the exercise is wrong and needs to be made larger before the module is written.

- [ ] **Step 2: Write the module**

Eight sections. Concepts: what occupies context; what compaction costs; clearing as routine; scoping reads; delegating side quests; the symptoms of a session that has lost the thread. Pay off the token tax introduced in Module 2.

Mechanics table: verified Claude Code commands from Step 1's session; Cursor and Copilot `not yet verified`.

- [ ] **Step 3: Write the exercise and verification**

Exercise: implement sign-up and log-in twice — naive, then disciplined. Use Django's built-in auth; do not hand-roll password hashing.

Verification: sign-up and log-in work and are tested; the learner names what filled context the first time and which specific technique they applied the second.

- [ ] **Step 4: Commit**

```bash
git add modules/03-context-management.md
git commit -m "Add Module 3: context management"
```

---

### Task 9: Learner-facing README and progress template

**Files:**
- Modify: `README.md`
- Create: `progress-template.md`

**Interfaces:**
- Consumes: modules 0–3.
- Produces: the fresher's entry point.

- [ ] **Step 1: Rewrite README with a Start here section first**

Above everything else: prerequisites, clone, set up the seed, open Module 0. A fresher must not have to read the syllabus to find step one.

- [ ] **Step 2: Mark availability honestly per module**

The syllabus table gets a status column. Modules 0–3 `available`; 4–7 `in build — <date>`. State plainly that a learner who reaches Module 4 before it lands should pause. This is the mitigation for the fast-learner wall.

- [ ] **Step 3: Write `progress-template.md`**

A dated table — module, date, verdict, what was hard — the learner copies into their working repo and fills in as they go.

- [ ] **Step 4: Note the solo-learner caveat in the contract**

`templates/review-contract.md` tells a reviewer with no written spec to derive criteria and have
**the author** confirm them. A learner working alone has no author, and an unconfirmed derived list
launders inexperience into a verdict. Add to its *When there is no written spec* section:

```markdown
**Working alone?** The confirmation step is not optional. If there is nobody to confirm your derived
criteria, use this contract only where a written spec already exists, and treat everything else as
backlog rather than reviewing against your own guess.
```

- [ ] **Step 5: Commit**

```bash
git add README.md progress-template.md templates/review-contract.md
git commit -m "Rewrite README for learners; add progress template; note the solo-learner caveat"
```

---

### Task 10: End-to-end dry run

**Files:**
- Modify: whatever the dry run breaks.

**Interfaces:**
- Consumes: everything.
- Produces: the go/no-go for day 6.

- [ ] **Step 1: Clone fresh and work Module 0 as a learner**

```bash
cd /tmp && rm -rf dryrun && git clone /Users/awais.qureshi/Documents/devstack/ai-on-boarding dryrun
cd dryrun
```

Follow the README only. Use no knowledge from having built it. Every point where you have to guess is a defect in the content.

- [ ] **Step 2: Work Modules 1, 2 and 3 the same way**

Time each. If Module 3 exceeds its ~3.5h estimate by more than an hour, correct the estimate rather than the module.

- [ ] **Step 3: Fix everything the dry run surfaced**

Commit fixes individually with messages naming what the dry run exposed.

- [ ] **Step 4: Record the result**

Append to the plan: modules verified, actual timings, defects found and fixed, anything still open. Do not describe a module as ready if it was not completed end to end.

- [ ] **Step 5: Final push and hand to review**

```bash
git push -u origin pilot/five-day-build
```

Report to Awais: what is ready, what is not, measured timings, and the one open operational dependency — **who pairs with the freshers for Module 3**, which lands in their first week.

---

## Deferred past the pilot

| Item | When |
|---|---|
| Modules 4–7 | During the cohort's first two weeks, staying ahead of learners |
| Cursor and Copilot mechanics columns | After the pilot, with parity testing |
| Runner skill (`runner-prompt.md`, `skills/`) | After module content stabilises |
| Reference solutions | After the pilot; the supervising pair is the escape hatch |
| Tier 2 tool tables | Documentation only, no learner impact |
