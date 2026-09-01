## 1. The form

- [x] 1.1 Add a second new-password entry to the reset page template, labelled so it reads as a
  confirmation of the first, and verify by following a live reset link that the page offers two
  separate password entries
- [x] 1.2 Confirm neither entry is echoed back into the form on a refused submission, by
  submitting a refused password and verifying the rendered page contains neither entry's text

## 2. Submission handling

- [x] 2.1 Read the second entry from the submission and compare it against the first, refusing
  the submission when they differ - re-render the form with a message saying the entries do not
  match, and verify by submitting two differing entries that the page reports the mismatch and
  still offers a form
- [x] 2.2 Place the comparison after the existing link-state check and before the strength check,
  and verify by submitting differing entries against a dead link that the page reports the link
  refusal rather than the mismatch
- [x] 2.3 Verify the ordering from the other side: submit two differing entries where the first is
  also too weak, and confirm the page reports only the mismatch
- [x] 2.4 Verify a mismatched submission never reaches the completion step - submit differing
  entries, then follow the same link again and confirm it is still usable and the account still
  authenticates with its previous password
- [x] 2.5 Confirm the JSON completion endpoint is untouched - `POST` a completion carrying a code
  and a single password with no confirmation field and verify it still succeeds
- [x] 2.6 Confirm the shared completion routine was not modified, by checking it against `git
  diff` - a change there means the design was not followed

## 3. Tests (after implementation, from the spec)

- [x] 3.1 List every requirement in `specs/user-password-reset/spec.md` from this change - the
  modified *Serve a page at the delivered link* and the five added requirements - and what a test
  would need to assert, working only from the spec
- [x] 3.2 Write the tests into `sdd_django_demo/api/test_password_reset.py` from that list,
  covering each requirement, with a test asserting directly that a mismatched submission leaves
  the reset link usable rather than letting that ride on a success path
- [x] 3.3 Update the existing tests that submit the reset form so they send both entries, and
  verify the reason each one changed is the added field and nothing else
- [x] 3.4 Run `pytest` for the whole project and confirm every test passes
- [x] 3.5 Prove the ordering test can actually fail - swap the mismatch and strength checks
  locally, confirm the test that pins mismatch-before-strength fails, then restore the order

## 4. Traceability and review

- [x] 4.1 Build `traceability.md` mapping every requirement from this change to its code and test
- [x] 4.2 Run `/code-review` and record the verdict
- [x] 4.3 Fix any blocking findings, each cited to a requirement, a named failing test, or a
  documented convention
- [x] 4.4 Run `/code-review` again (round 2, verify-only) and confirm `Ready to merge: yes`
