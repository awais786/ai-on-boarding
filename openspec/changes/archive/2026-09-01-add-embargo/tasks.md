## 1. Embargo app and models

- [x] 1.1 Create the `embargo` Django app and register it in `INSTALLED_APPS`; verify
  `python manage.py check` passes
- [x] 1.2 Create a blocked-country model in `embargo/models.py`: `country` (unique)
- [x] 1.3 Create an account-country model in `embargo/models.py`: `user` (one-to-one to
  `auth.User`), `country`
- [x] 1.4 Generate and apply the migration for the `embargo` app

## 2. Embargo checks

- [x] 2.1 Implement a country-blocked check in `embargo` (case-insensitive lookup against the
  blocked-country model); verify from a shell it returns the right answer for a seeded and an
  unseeded country
- [x] 2.2 Implement a function that records an account's submitted country (creates/updates the
  account-country row for that user)
- [x] 2.3 Seed India as a blocked country via a data migration in `embargo/migrations/`; verify
  the blocked-country model contains it (case-insensitively) after migrating

## 3. Signup integration

- [x] 3.1 Add a required, non-blank `country` field to `SignupSerializer` in
  `sdd_django_demo/api/serializers.py`
- [x] 3.2 Add a `validate_country` step calling the embargo check, raising the same field-keyed
  `ValidationError` pattern `validate_email` already uses, naming `country`
- [x] 3.3 Update `SignupSerializer.create()` to pop `country` from validated data, create the
  `User` as before, then record the account's country via embargo's recording function
- [x] 3.4 Update `SignupView`'s `@extend_schema` request/response annotations for the new field
  (verified already satisfied: `request=SignupSerializer` introspects the field automatically -
  confirmed via generated schema - and the 400 description already generically names "the
  offending field")

## 4. Signin integration

- [x] 4.1 In `SigninView.post`, after `authenticate()` succeeds, check the authenticated
  account's recorded country against embargo (an account with no recorded country is treated as
  allowed); if blocked, return the existing `SIGNIN_REJECTION_BODY` at 401 without creating a
  token and without touching `SigninAttempt.failed_count`/`last_failed_at`
- [x] 4.2 Confirm by inspection that the embargo-rejection branch shares no code path with the
  failed-password counter update (tests for this come in section 5)

## 5. Tests (after implementation, from the spec)

- [x] 5.1 List every requirement in `specs/embargo/spec.md` and in this change's `user-signup`
  and `user-signin` deltas, and what a test would need to assert, working only from the spec
- [x] 5.2 Write `embargo/test_rules.py` from that list, covering embargo's own requirements:
  unlisted country allowed, listed country blocked, case-insensitive match, a later addition and
  a later removal each taking effect on the next check
- [x] 5.3 Extend `sdd_django_demo/api/test_signup.py` for the new requirements: missing country
  rejected and names the field, blocked country (e.g. India) rejected and names the field,
  unblocked country allowed, no account created for a blocked-country submission
- [x] 5.4 Extend `sdd_django_demo/api/test_signin.py` for the new requirements: signin for an
  embargoed account is rejected identically (status and body) to a wrong-password rejection, an
  account whose country is blocked after signup is rejected on its next signin, an account whose
  country is later unblocked can sign in again, an embargoed rejection does not change
  `SigninAttempt.failed_count`
- [x] 5.5 Run `pytest` and confirm all tests pass, including every pre-existing test
- [x] 5.6 Break the identical-rejection guarantee on purpose (e.g. make the embargo rejection at
  signin return a distinct body) and confirm the matching test goes red, then restore

## 6. Traceability and review

- [x] 6.1 Build `traceability.md` mapping every requirement (embargo, plus the user-signup and
  user-signin deltas) to its code and test
- [x] 6.2 Confirm the GitHub issue for this change exists (issue #15, per `openspec/config.yaml`)
  and post the proposal and full delta specs to it via `gh issue comment`
- [x] 6.3 Run `/code-review`
- [x] 6.4 Fix any blocking findings and re-review once (two passes max) until
  `Ready to merge: yes` (no blocking findings on the first pass - both findings were non-blocking
  nits on pre-existing code, so no fix or follow-up pass was needed)
