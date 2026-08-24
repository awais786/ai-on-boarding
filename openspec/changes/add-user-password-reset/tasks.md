## 1. Reset code storage

- [x] 1.1 Create the reset code model in `sdd_django_demo/api/models.py`: the account it belongs
  to, a digest of the code, the issue time, and a marker for whether it is still usable - verify
  by importing it in a Django shell and creating a row
- [x] 1.2 Add a helper that issues a code for an account: generate with `secrets.token_urlsafe`,
  store only its digest, and mark every earlier unused code for that account dead - verify the
  helper returns the plain code and leaves exactly one usable row
- [x] 1.3 Add a helper that resolves a submitted code to a usable record or to nothing, applying
  the 30-minute window and the used/superseded marker in one place - verify it returns nothing
  for each of the four unusable cases
- [x] 1.4 Generate and apply the migration and verify `python manage.py migrate` runs clean

## 2. Request a reset

- [x] 2.1 Add a serializer for the reset request accepting `email`, required and non-blank -
  verify a missing email produces a field-keyed error
- [x] 2.2 Configure the email backend so the project still needs no environment variables:
  console in development, locally-held under test - verify by checking the outbox in a shell
- [x] 2.2a Add the reset base-URL setting with a working local default, so the link's scheme and
  host never come from the request - verify a shell call builds an absolute link from it
- [x] 2.3 Implement the reset-request view: validate the email's shape, look up the account,
  issue and send a code only when one exists, and return the same fixed HTTP 200 body from a
  single return statement either way - verify registered and unregistered addresses give
  byte-identical responses
- [x] 2.4 Compose the message so it carries an absolute link built from the 2.2a setting with the
  plain code embedded in it, and the response never does - verify the link reaches the outbox,
  starts with a scheme and host, and that neither link nor code appears in the response body
- [x] 2.5 Add the reset-request route to `sdd_django_demo/api/urls.py` and verify it resolves

## 3. Complete a reset

- [x] 3.1 Add a serializer for the completion accepting a reset code and a new password, both
  required and non-blank, applying signup's existing password validator to the new password by
  importing it rather than restating the rules - verify a weak password is refused by the same
  message signup uses
- [x] 3.2 Implement the completion view: resolve the code through the 1.3 helper, and on failure
  return the one fixed HTTP 400 body - verify all four unusable-code cases return identical
  responses
- [x] 3.3 On success set the new password, mark the code used, and delete the account's
  authentication token rows - verify the account authenticates with the new password, not the
  old one, and that a token held beforehand is gone
- [x] 3.4 Add the completion route to `sdd_django_demo/api/urls.py` and verify it resolves
- [x] 3.5 Add drf-spectacular schema annotations for both endpoints' success and failure
  responses - verify `/api/schema/` renders without warnings

## 4. Tests (after implementation, from the spec)

- [x] 4.1 List every requirement in `specs/user-password-reset/spec.md` and what a test would
  need to assert, working only from the spec
- [x] 4.2 Write `sdd_django_demo/api/test_password_reset.py` from that list
- [x] 4.3 Assert the registered and unregistered reset-request responses are byte-identical in
  status and body, not merely both 200
- [x] 4.4 Assert all four unusable-code refusals (unrecognised, expired, used, superseded) are
  byte-identical, not merely all 400
- [x] 4.5 Assert the security-sensitive behaviour directly rather than through a success path:
  neither the code nor the link carrying it ever appears in a response, the stored code is a
  digest and not the code, the stored password is not the submitted text, and a pre-existing
  authentication token stops working
- [x] 4.6 Assert no message is sent for an unregistered address
- [x] 4.6a Assert the delivered link is absolute - scheme and host present - and that its host
  comes from the setting rather than from the request, by sending the request with a different
  Host and confirming the link is unchanged
- [x] 4.7 Run `pytest` and confirm the whole project passes, including `test_signup.py`
- [x] 4.8 Break the identical-refusal guarantee on purpose (make the expired case return a
  distinct message) and confirm the matching test goes red, then restore it

## 5. Traceability and review (sections 1-4)

This section records the review of the API endpoints. Sections 6 and 7 were added
afterwards, so the passes below did not see the reset page - section 8 covers it.

- [x] 5.1 Build `traceability.md` mapping every requirement to its code and test
- [x] 5.2 Run `/code-review`
- [x] 5.3 Fix any blocking findings and re-review once (two passes max) until the verdict is
  `Ready to merge: yes`

## 6. Reset page at the delivered link

- [x] 6.1 Extract the completion sequence (claim the code, set the password, delete the
  account's tokens) from the API view into one routine both entry points call - verify the
  existing API tests still pass unchanged
- [x] 6.2 Add a template with a new-password form, a not-usable message, and a success message -
  verify it renders for each of the three states
- [x] 6.3 Add the page view: GET resolves the code and shows the form or the not-usable message;
  POST validates with signup's password validator and completes through the 6.1 routine - verify
  by following a real link in a browser
- [x] 6.4 Route `reset-password/<code>/` at the project level, matching the address the mail
  carries - verify a delivered link resolves instead of 404ing
- [x] 6.5 Keep the page out of the OpenAPI schema - verify `manage.py spectacular` still reports
  no new warnings

## 7. Tests for the reset page (after implementation, from the spec)

- [x] 7.1 Assert a usable link returns 200 and offers a password field
- [x] 7.2 Assert submitting the form completes the reset and the account authenticates with the
  new password
- [x] 7.3 Assert all four unusable-code causes produce the same page text and no form
- [x] 7.4 Assert a weak password keeps the form open and leaves the old password working
- [x] 7.5 Assert the page cannot be used twice, and that a token held beforehand is gone after it
- [x] 7.6 Run `pytest` and confirm the whole project passes

## 8. Review of the reset page

- [x] 8.1 Extend `traceability.md` with the page requirement, its code and its tests
- [x] 8.2 Run `/code-review` over sections 6 and 7
- [x] 8.3 Fix any blocking findings and re-review once (two passes max) until the verdict is
  `Ready to merge: yes`

## 9. Survive a failed delivery, and cap requests per address

- [x] 9.1 Wrap issuing and sending in one transaction so a delivery failure rolls the issuance
  back - verify that with sending forced to fail, a previously delivered code still resolves and
  no new row is left behind
- [x] 9.2 Limit the reset-request endpoint per submitted email address, applying the limit
  whether or not an account exists - verify a registered and an unregistered address are answered
  identically once each is limited
- [x] 9.3 Put the rate in settings so it can be changed without touching the view, keeping the
  project's no-environment-variables constraint - verify the view honours an overridden rate

## 10. Tests for section 9 (after implementation, from the spec)

- [x] 10.1 Assert a failed delivery leaves an earlier unused code usable and adds no row
- [x] 10.2 Assert a failed delivery is answered identically to a successful one
- [x] 10.3 Assert requests beyond the limit issue no code and send no message
- [x] 10.4 Assert a flood cannot leave an address with no usable code - the last code
  delivered stays usable once the limit stops the superseding
- [x] 10.5 Assert reaching the limit answers registered and unregistered addresses identically
- [x] 10.6 Run `pytest` and confirm the whole project passes

## 11. A uniform response when the limit refuses a request

- [x] 11.1 Return a fixed body for a request the per-address limit refuses, dropping the wait
  remaining that the framework appends - verify two refusals taken a second apart are
  byte-identical in status and body
- [x] 11.2 Keep the fixed body in the same shape as the endpoint's other bodies, defined once
  beside them rather than inline at the raise - verify the constant is not mutated by a response
  that carries it

## 12. Tests for section 11 (after implementation, from the spec)

- [x] 12.1 Assert two refusals separated in time are identical in status and body, and that the
  body carries no countdown
- [x] 12.2 Rewrite `test_being_limited_does_not_reveal_whether_an_account_exists` to assert
  equality outright - it currently compares two separately-timed bursts whose bodies embed a
  rounded countdown, so it can fail for a reason unrelated to what it checks
- [x] 12.3 Assert the refused status is 429
- [x] 12.4 Run `pytest` and confirm the whole project passes

## 13. Review cleanup (raised in review, no requirement attached)

- [x] 13.1 Document 429 in the reset-request endpoint's OpenAPI annotation and drop "always"
  from the 200 description - verify `manage.py spectacular` still reports no warnings
- [x] 13.2 Correct the comment above the response constants: passing the constant to `Response`
  shares the module-level dict, it does not make `response.data` the module object
- [x] 13.3 Replace the locally-defined `explode` in `test_password_reset.py` that duplicates the
  module-level `_explode` with `_explode` itself. Only one of the two locals is a duplicate: the
  other raises `IntegrityError` against a different patch target, so it stays
- [x] 13.4 Remove the unreachable `return None` at the end of `PasswordResetCode.issue_for` -
  every loop path already returns or raises. Deleting the line alone makes pylint report
  `inconsistent-return-statements`, since it cannot prove the counter loop always exits, so the
  retry is restructured as an explicit try/retry that provably does

## 14. A malformed request body must not reach the limit's key

- [x] 14.1 Stop a body that is not a JSON object from raising inside the per-address limit's
  key. The limit runs before any serializer, so the body reaches it unvalidated - verify a list,
  a string and a number each return the same 400 the confirm endpoint already returns for them,
  rather than raising
- [x] 14.2 Confirm that skipping the limit for a body carrying no address opens nothing: such a
  request is refused before it can issue or send - verify a flood of malformed bodies issues no
  code, sends no message, and leaves the address's own allowance untouched

## 15. Tests for section 14 (after implementation, from the spec)

- [x] 15.1 Assert a list, a string and a number body are each refused rather than raising
- [x] 15.2 Assert a malformed body issues no code and sends no message
- [x] 15.3 Run `pytest` and confirm the whole project passes

## 16. Close the gaps review left open (nits, non-blocking)

- [x] 16.1 Assert the refusal carries no retry-after header. Dropping it is half of why
  `wait=None` is passed, and the code comment says so, but only the body is asserted - a
  regression restoring the header while leaving the detail string alone would stay green
- [x] 16.2 Exercise `PasswordResetCode.issue_for`'s retry branch, which nothing currently
  reaches: the one test that could patches `issue_for` out wholesale. Verify a collision on the
  partial unique index is retried and still yields a usable code
- [x] 16.3 Correct the traceability row for *Reject a reset request with no email* - the
  malformed-body tests do not demonstrate its "names the email field" scenario, since a
  non-object body is answered with `non_field_errors`. They belong on their own line
- [x] 16.4 Record on `RESET_LIMITED_BODY` that only its `detail` reaches the response, so a
  second key added to it would silently not appear
