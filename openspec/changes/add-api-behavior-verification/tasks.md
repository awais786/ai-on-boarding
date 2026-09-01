## 1. Tooling scaffold

- [ ] 1.1 Create `tooling/api-verification/` with its own Python requirements file (the Anthropic
  SDK, PyYAML, and an HTTP client) and a Node manifest pinning the OpenAPI-to-Postman converter
  and the collection runner to exact versions, and verify a clean install of both succeeds and
  each command-line tool reports the pinned version
- [ ] 1.2 Give the tooling its own pytest configuration so it is a self-contained suite separate
  from the Django project's, and verify running it collects without error and that running the
  Django project's suite is unaffected

## 2. Coverage derivation and completeness

- [ ] 2.1 Write the route enumerator that walks Django's URL resolver and emits every routed
  address with its methods, and verify its output lists the five API operations, both methods of
  the reset page, the admin site, and the two schema-serving addresses
- [ ] 2.2 Generate the OpenAPI description into a build directory, in a mode that does not treat
  the known health-endpoint generation error as fatal, and verify the five API operations appear
  in the generated file
- [ ] 2.3 Write `surfaces.yaml` declaring the reset page as a spec-bearing surface the description
  omits, and excluding the admin site and the schema-serving addresses with a written reason each,
  and verify a loader rejects an exclusion whose reason is empty
- [ ] 2.4 Write the completeness check - routed addresses minus described minus declared minus
  excluded must be empty - and verify it exits zero against the current tree, then add a
  throwaway route, confirm the check exits non-zero and names that address, and remove it

## 3. The check library

- [ ] 3.1 Define the library format - one file per capability, each entry naming its requirement
  and scenario verbatim, holding an ordered sequence of requests with checks attached to the
  request that can observe them - and verify the loader rejects an entry whose requirement name
  does not appear in the matching promoted spec
- [ ] 3.2 Write the checks for `user-signup` from `openspec/specs/user-signup/spec.md`, working
  from the spec text, and verify every requirement in that spec is either covered by an entry or
  recorded in the register
- [ ] 3.3 Write the checks for `user-signin` the same way, including the sequence that compares
  the three refusals against each other and the sequence that drives an address into lockout, and
  verify the same coverage condition holds for that spec
- [ ] 3.4 Write the checks for `user-password-reset` the same way, including the sequences that
  follow a delivered link, submit two entries to the page, and confirm a mismatch leaves the link
  usable, and verify the same coverage condition holds for that spec
- [ ] 3.5 Write `unobservable.yaml` recording each requirement or scenario that cannot be judged
  from outside the process, each with one of the three categories, a reason, and the test that
  covers it instead, and verify every entry resolves to a requirement or scenario that exists in a
  promoted spec and names a category from that set
- [ ] 3.6 Write the collection builder that converts the description, attaches the library's
  sequences and checks, appends the declared surfaces, and gives any operation with no entry a
  default status-code check, and verify the built collection holds a request for every described
  operation and every declared surface

## 4. Execution against a live instance

- [ ] 4.1 Write the run script that starts the mail catcher, starts the server with the existing
  `RESET_SMTP_*` settings pointed at it, waits for both to answer before proceeding, executes the
  collection with the JSON reporter, and stops both afterwards, and verify it produces a report
  locally with every check passing
- [ ] 4.2 Give every sequence run-unique account addresses so the reset rate limit and the signin
  lockout cannot leak between sequences, and verify by running the script twice in succession
  against the same database that both runs produce the same result
- [ ] 4.3 Verify the reset sequences take the code from the delivered message rather than from any
  response, and that the check asserting the reset-request response does not carry the code is
  present and passes

## 5. Evaluation and the gate

- [ ] 5.1 Write the evaluation step that reads the promoted specs, the built collection, the check
  library, the register, and the run report, asks `claude-opus-5` with adaptive thinking and a
  fixed output schema for its findings, and writes them as JSON, and verify each finding carries
  either the name of a promoted requirement or none
- [ ] 5.2 Make the evaluation fail with a message naming what is missing when its credential is
  absent, rather than skipping, and verify by running it with the credential unset that it exits
  non-zero and names the credential
- [ ] 5.3 Write the gate that fails on a completeness failure, on any failed check in the report,
  on an evaluation that could not run, and on a finding naming a requirement absent from the
  register - and reports a finding naming no requirement without failing - and verify each of
  those five branches produces the intended exit status against a crafted input

## 6. The workflow

- [ ] 6.1 Add the GitHub Actions workflow triggered on push to `main` and on manual dispatch,
  running the same commands the local run script runs, and verify the file parses and that its
  step commands match the script's line for line
- [ ] 6.2 Have the run publish the generated description, the built collection, the run report,
  and the findings as artifacts of the run, and verify they are produced by the local run in the
  same paths the workflow uploads

## 7. Documentation

- [ ] 7.1 Write `tooling/api-verification/README.md` stating which part supplies the endpoint set,
  which part supplies expected behaviour, what executes the checks, what the evaluation judges,
  and the exact conditions under which a run fails, and verify it answers both documentation
  scenarios in the delta spec without the reader opening any tooling file
- [ ] 7.2 Document what a contributor does when a run fails on a coverage gap - add a check, or
  add a register entry with a category and reason - and verify the instruction names both options
  and where each is written
- [ ] 7.3 Link the tooling README from `README.md` and `sdd_django_demo/README.md`, and verify
  both links resolve to the file

## 8. Tests (after implementation, from the spec)

- [ ] 8.1 List every requirement in this change's `specs/api-behavior-verification/spec.md` and
  what a test would need to assert for each, working only from the spec
- [ ] 8.2 Write the tests into `tooling/api-verification/tests/` from that list, covering each
  requirement, naming each test after the behaviour it protects
- [ ] 8.3 Assert directly, not through a success path, that the evaluation fails rather than
  passes when its credential is absent, and that a run whose report holds a failed check cannot
  exit zero
- [ ] 8.4 Run the tooling suite and the Django project's suite and confirm every test in both
  passes
- [ ] 8.5 Prove at least one new test can actually fail - remove a check entry whose requirement
  is not in the register, confirm the gate goes red and names that requirement, then restore it

## 9. Traceability and review

- [ ] 9.1 Build `traceability.md` mapping every requirement in this change to the file that
  implements it and the test that covers it
- [ ] 9.2 Run `/code-review` and record the verdict
- [ ] 9.3 Fix any blocking findings, each cited to a requirement, a named failing test, or a
  documented convention
- [ ] 9.4 Run `/code-review` again (round 2, verify-only) and confirm `Ready to merge: yes`
