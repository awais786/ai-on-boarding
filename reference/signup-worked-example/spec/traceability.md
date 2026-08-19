# Traceability: User Signup

Every requirement in `spec.md`, the task that implements it, the code that satisfies it, and the
test that proves it. Built by hand — Spec Kit labels tasks by user story, so nothing generates
the Task column for you.

| Requirement | Task | Code | Test |
|---|---|---|---|
| FR-001 accepts username, email, password | T001 | `api/serializers.py:16-23` | `test_fr001_accepts_username_email_and_password` |
| FR-002 username absent or empty rejected | T001 | `api/serializers.py:16` | `test_fr002_fr003_fr004_missing_required_field_is_rejected[username]`, `…_empty_…[username]` |
| FR-003 email absent or empty rejected | T001 | `api/serializers.py:17` | `…_missing_required_field_is_rejected[email]`, `…_empty_…[email]` |
| FR-004 password absent or empty rejected | T001 | `api/serializers.py:18-22` | `…_missing_required_field_is_rejected[password]`, `…_empty_…[password]` |
| FR-005 malformed email rejected | T002 | `api/serializers.py:17` (`EmailField`) | `test_fr005_malformed_email_is_rejected` |
| FR-006 duplicate username rejected | T004 | `api/serializers.py:25-28` | `test_fr006_duplicate_username_is_rejected` |
| FR-007 duplicate email rejected | T005 | `api/serializers.py:30-33` | `test_fr007_duplicate_email_is_rejected` |
| FR-008 password below 8 characters rejected | T003 | `api/serializers.py:20` | `test_fr008_password_shorter_than_minimum_is_rejected`, `…_at_the_minimum_is_accepted` |
| FR-009 exactly one account created | T006 | `api/serializers.py:35-40` | `test_fr009_valid_submission_creates_exactly_one_account` |
| FR-010 password not recoverable from storage | T006 | `api/serializers.py:36` (`create_user`) | `test_fr010_password_is_not_recoverable_from_storage` |
| FR-011 password never in a response | T007 | `api/serializers.py:43-48` | `test_fr011_password_never_appears_in_a_response` |
| FR-012 rejection identifies the field | T010 | `api/views.py:31-32` | `test_fr012_rejection_identifies_the_offending_field` |
| FR-013 success distinguishable by status | T008 | `api/views.py:31-34` | `test_fr013_success_and_rejection_differ_by_status` |
| FR-014 email uniqueness case-insensitive | T005 | `api/serializers.py:31` (`email__iexact`) | `test_fr014_email_uniqueness_is_case_insensitive` |
| FR-015 success returns 201 | T008 | `api/views.py:34` | `test_fr015_successful_signup_returns_201` |

## What the table exposes

**T001 carries four requirements.** FR-001 through FR-004 all resolve to "declare the three
fields, required and non-blank". That is not wrong, but it means one task's failure would break
four requirements, and a reviewer reading `tasks.md` alone would never see it.

**Two requirements share a line of code.** FR-005 and FR-003 both rest on the `EmailField`
declaration — one for presence, one for format. They are genuinely different requirements with
genuinely different tests, and a single edit could break both.

**No requirement is untested and no test is unrequired.** Fifteen requirements, twenty test
cases — the excess is parametrisation over the three fields, not extra behaviour.

## Proof the tests can fail

On 19 August 2026, three requirements were broken deliberately:

| Break | Test that caught it |
|---|---|
| Removed `min_length` from the password field | `test_fr008_password_shorter_than_minimum_is_rejected` |
| Changed `email__iexact` to `email` | `test_fr014_email_uniqueness_is_case_insensitive` |
| Returned 200 instead of 201 | `test_fr015_successful_signup_returns_201` |

Result: **3 failed, 17 passed.** Each break was caught by its own test and by no other, which is
what makes the remaining green meaningful.
