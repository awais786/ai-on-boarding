# API behaviour verification

Checks, on every push to `main`, that the API's real HTTP behaviour matches what
`openspec/specs/` says it should do.

`pytest` proves the Django code satisfies its specs from inside the process. This proves the
running API does, from outside it — over HTTP, the way a caller reaches it.

## Where each part of the answer comes from

This is the thing to know before adding an endpoint or a requirement. Four sources, and each
answers exactly one question:

| Source | Answers | Where it lives |
|---|---|---|
| The OpenAPI description | *Which endpoints exist?* | generated from the code by `manage.py spectacular` |
| `surfaces.yaml` | *What else is routed, and why is it in or out?* | this directory |
| `openspec/specs/` | *How must they behave?* | the promoted specs — the only source of expected behaviour |
| `checks/` | *What do we send, and what must hold?* | this directory, one file per capability |
| The evaluation | *Are those checks a faithful reading of the specs?* | `verify/evaluate.py` |

**Endpoint coverage is never hand-maintained.** Add an endpoint to the API, and it appears in the
description and is exercised on the next run with no edit here. Remove one, and it stops being
exercised. Nobody keeps a list in step.

**Expected behaviour is never inferred from the code.** A check names, verbatim, the requirement
and scenario it verifies, and the loader refuses a name that does not appear in the promoted spec.
If the code does something no spec describes, no check asserts it.

## Why `surfaces.yaml` exists

The description only knows about endpoints served through the API framework. The page served at a
delivered reset link is a plain page — deliberately so — and carries eight promoted requirements
the description cannot see.

So coverage is proven rather than assumed. A build step lists every address Django routes and
subtracts three sets:

```
routed addresses
  − present in the OpenAPI description        ← automatic
  − declared in surfaces.yaml                 ← carries requirements, description omits it
  − excluded in surfaces.yaml, with a reason  ← carries no requirements
  ─────────────────────────────────────────
  = must be empty, or the run fails
```

A new address that is in none of the three stops the run and names itself. That is what keeps the
declared list honest: it cannot quietly fall behind.

## Why `unobservable.yaml` exists

Some requirements cannot be judged by watching HTTP during a run. Each is recorded by name, with a
category, a reason, and the test that covers it instead:

- **`time-bound`** — needs the clock advanced past the run (a code expiring after 30 minutes).
- **`storage-internal`** — asserts on what is stored, not what is returned (a password stored
  unrecoverably).
- **`induced-failure`** — needs a fault injected beneath the application (delivery failing).
- **`concurrency`** — needs genuinely simultaneous requests, which a runner issuing one after
  another cannot produce.

An entry here does not fail a run and is not reported as missing coverage. It is a division of
labour, not an exemption — which is why every entry must name the test that covers it.

## Why a mail catcher

*Never return the reset code in a response* is itself a requirement, so the code exists only in the
message. The run points delivery at a mail catcher using the `RESET_SMTP_*` settings the project
already reads, and the collection asks the catcher for the message — exactly as a recipient reads
their mail. Twelve password-reset requirements depend on holding a usable code.

Nothing about the application changes. The check that the reset-request response does *not* carry
the code stays in place and is asserted directly, so reading the code this way cannot mask a
regression in the requirement that forbids returning it.

## When does a run fail?

```
coverage incomplete against routed addresses  ──▶ fail    deterministic
any check failed against the live API         ──▶ fail    deterministic
the evaluation could not run                  ──▶ fail    deterministic
a finding naming a promoted requirement,
  and that requirement is not in the register ──▶ fail    judged
a finding naming no requirement               ──▶ reported, does not fail
```

The last two lines are the same distinction this project already applies to code review: a finding
blocks when it cites a requirement, and is a nit otherwise (`openspec/config.yaml`).

The register is what makes the judged half safe on the critical path. A gap someone has classified
and written down does not fail the run; a requirement nobody has classified does. Coverage can
only be given up deliberately, in a file a reviewer sees.

## When a run fails on a coverage gap

The evaluation reports a requirement with no check. There are exactly two honest responses, and
the run stays red until you pick one:

1. **Write the check.** Add an entry to the capability's file in `checks/`, naming the requirement
   and scenario verbatim. This is the answer whenever the behaviour is observable over HTTP.
2. **Record it as unobservable.** Add an entry to `unobservable.yaml` with one of the four
   categories, the reason it cannot be judged from outside the process, and the `pytest` test that
   covers it instead. This is the answer only when no sequence of HTTP requests could show it.

There is no third option. Deleting the check, loosening an assertion, or widening an exclusion to
make the run green removes the coverage the failure is telling you about.

## Adding an endpoint

1. Implement it. If it is served through the API framework, it enters the description and is
   exercised on the next run — no edit here. If it is not, the completeness check will stop the
   run and name it; declare it in `surfaces.yaml`.
2. Write its requirements in its capability spec and get them promoted into `openspec/specs/`.
3. Add checks in `checks/<capability>.yaml` for the requirements that are observable over HTTP,
   and register the ones that are not.

Until step 2, the endpoint is exercised but judged only by a default status-code check — the
description says what statuses it documents, and nothing more is asserted, because nothing more is
specified.

## Running it

```bash
cd tooling/api-verification
python -m venv .venv
.venv/bin/pip install -r ../../sdd_django_demo/requirements.txt -r requirements.txt
npm install

./run.sh                                        # generate, check coverage, build, execute
.venv/bin/python -m verify.evaluate             # needs ANTHROPIC_API_KEY
.venv/bin/python -m verify.gate --skip-completeness
```

These are the same three commands the workflow runs, so a CI failure reproduces here.

`run.sh` needs `mailpit` on `PATH`. It writes everything to `build/` and never touches the
project's own database — it uses `build/verification.sqlite3` via a settings module that imports
the project's settings unchanged and overrides only the database path.

## Layout

```
checks/               behavioural checks, one file per capability
surfaces.yaml         non-API surfaces that carry requirements; addresses that carry none
unobservable.yaml     requirements no HTTP run can judge, with the test that covers each
verify/routes.py      every address Django routes
verify/completeness.py  proves the endpoint set complete, or fails the run
verify/build.py       assembles the collection from description + checks + surfaces
verify/evaluate.py    judges the checks against the specs
verify/gate.py        decides whether the run passes
run.sh                the whole chain, locally
```

We write no JavaScript here. The OpenAPI-to-collection converter and the collection runner are
Node programs invoked as commands, pinned in `package.json`.

## Requirements

This tooling is itself specified. Its requirements are in
`openspec/specs/api-behavior-verification/spec.md` once promoted, and until then in
`openspec/changes/add-api-behavior-verification/`. Its own tests are in `tests/`, run with
`.venv/bin/python -m pytest` from this directory.
