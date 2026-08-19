# Phase 9 — Submit your work

## What you'll do

Assemble the evidence that you built what you specified, run a self-audit, and hand it in.

Not paperwork. This is the last piece of the discipline: **"it works on my machine" is not
evidence, and neither is a green test suite.** Evidence is a chain from requirement to
implementation to a test that could fail.

## Time

About 30 minutes.

## Before you start

Phase 8 complete: signup and signin both built, specified, tested and traced.

## Steps

### 1. Self-audit

Answer each of these with a file and a line number, not a yes:

- Where is every requirement in your specification listed? → `traceability.md`
- Which requirement has the weakest test? Name it. (Every project has one.)
- Which requirement did you decide arbitrarily, with no strong reason? Name it.
- What behaviour is in your code that no requirement asked for?
- Where do your specification and your OpenAPI schema disagree?
- Which of your tests would still pass if its requirement were violated? Check, do not guess.
- What did you add to `django-conventions`, and did it make signin cheaper than signup?
- For each change request you received: what did it touch, and did you update the specification
  before the code?
- Did you hand-write any code? Which, and which instruction should have produced it instead?

If any answer is "none", check again. "None" is usually "I did not look."

### 2. Prove one test can still fail

Pick the requirement you would least like to be wrong — probably password storage or the
duplicate-email rule.

Break the code that satisfies it. Run the suite. **A test must fail.** Restore:

```bash
git checkout -- .
```

Record which test failed and what you broke. That is your strongest single piece of evidence:
proof that at least one requirement is genuinely protected.

### 3. Write the submission note

Create `SUBMISSION.md`:

```markdown
# Submission

## What I built
Signup and signin, specified first, generated from those specifications.

## Evidence
- Specification: <path>
- Traceability table: traceability.md — <N> requirements, all with tests
- Test suite: `pytest` → <N> passed
- Failure proof: broke <what>, test <name> failed as expected

## Pull requests
- Signup: spec PR <link>, implementation PR <link>
- Signin: spec PR <link>, implementation PR <link>

## Change requests
- <what arrived, what it touched, and what I decided about scope>

## Skill
- Added to `django-conventions`: <what, and why>
- Corrections needed: signup <N>, signin <M>

## Hand-written code
<none, or: what I edited by hand and which instruction should have covered it>

## Decisions I made
- Password minimum: <N> characters, because <reason>
- Email case sensitivity: <decision>, because <reason>
- Success response: <what>, because <reason>
- <any other judgement call>

## What I would change
<one thing your specification gets wrong or leaves vague, that you have not fixed>

## Where I am unsure
<anything you decided arbitrarily and want a second opinion on>
```

The last two sections are the ones your reviewer will read first. A submission claiming
everything is perfect gets read with more suspicion than one that names its own weakest point.

### 4. Confirm the server runs

Your reviewer will run checks against a live server. Make sure it starts from a clean checkout:

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Confirm `http://127.0.0.1:8000/api/docs/` renders and lists signup and signin.

### 5. Commit and hand it in

```bash
git add .
git commit -m "Submit signup and signin"
git push
```

Then open your pull requests on GitHub and check the diffs show everything you expect. If a change
is missing, it was never pushed — and your lead would have reviewed the wrong thing.

## Done when

- [ ] `SUBMISSION.md` exists, with decisions and reasons
- [ ] It names your weakest test and one thing you would change
- [ ] `traceability.md` covers every requirement of both features
- [ ] You have broken a requirement's code and watched its test fail, and recorded which
- [ ] The server starts from a clean checkout and `/api/docs/` lists both endpoints
- [ ] Your commit is in, pushed, and visible in the pull request on GitHub

## What happens next

Your reviewer runs two things against your work:

1. **A conformance suite** — checks that hold for any correct signup, whatever your
   specification chose. You have not seen it, deliberately: if you had, you would have built to
   it instead of to your own specification, which is precisely the habit this exercise is trying
   to break.
2. **A review against your own specification** — does the code do what *you* said it would?

The second matters more. The first can only tell you that you built *a* signup. The second tells
you whether you built the one you specified.

## If it goes wrong

**You cannot name a weakest test.** Then you have not looked. Take any requirement, ask what the
test would have to assert to catch a violation, and compare that with what it actually asserts.

**Your specification and schema disagree and you do not know which is right.** That is a phase 6
question. Decide which one describes what the product should do, then fix the other.
