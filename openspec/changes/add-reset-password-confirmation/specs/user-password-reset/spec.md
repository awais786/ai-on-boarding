## MODIFIED Requirements

### Requirement: Serve a page at the delivered link
Following a delivered reset link SHALL return a page from which the recipient can choose a new
password, so that the link is usable by a person and not only by a programmatic client. The page
SHALL ask for the new password twice, so that a person who cannot see what they typed is not
committed to a password they did not intend.

#### Scenario: A usable link opens a form
- **WHEN** a link carrying a usable code is followed
- **THEN** the response is HTTP 200 and offers a form for choosing a new password

#### Scenario: The form asks for the new password twice
- **WHEN** a link carrying a usable code is followed
- **THEN** the form offers two separate entries for the new password

#### Scenario: Submitting the form completes the reset
- **WHEN** that form is submitted with an acceptable new password entered identically in both
  entries
- **THEN** the reset completes and the account authenticates with the new password

#### Scenario: An unusable link says so and offers no form
- **WHEN** a link carrying an unrecognised, expired, used, or superseded code is followed
- **THEN** the page reports that the link cannot be used, in the same words for all four causes,
  and offers no password form

#### Scenario: A weak password keeps the form open
- **WHEN** the form is submitted with a new password the system would reject, entered identically
  in both entries
- **THEN** the page reports the problem and the account keeps the password it had

## ADDED Requirements

### Requirement: Require the two password entries to match
The reset page SHALL change nothing unless the two entries hold the same password. When they
differ, the page SHALL report that they differ, keep the form open, leave the account with the
password it had, and leave the reset link usable so the person can try again.

#### Scenario: A mismatch is reported and changes nothing
- **WHEN** the form is submitted with two entries that differ
- **THEN** the page reports that the entries do not match, and the account still authenticates
  with the password it had

#### Scenario: A mismatch keeps the form open
- **WHEN** the form is submitted with two entries that differ
- **THEN** the page still offers a form for choosing a new password

#### Scenario: A mismatch does not spend the reset link
- **WHEN** the form is submitted with two entries that differ, and the same link is then followed
  again
- **THEN** the link is still usable and offers a form

#### Scenario: A second entry left empty is a mismatch
- **WHEN** the form is submitted with a new password in the first entry and nothing in the second
- **THEN** the account still authenticates with the password it had

### Requirement: Report a mismatch before judging the password
When the two entries differ, the page SHALL report only that they differ, even if the submitted
password would also have been refused as too weak. A person who has mistyped SHALL be told about
the mistyping rather than given a verdict on a password they did not mean to submit.

#### Scenario: A mismatch is reported ahead of a strength complaint
- **WHEN** the form is submitted with two entries that differ and a first entry the system would
  also refuse as too weak
- **THEN** the page reports that the entries do not match and does not report the weakness

#### Scenario: Strength is still judged once the entries match
- **WHEN** the form is submitted with two matching entries holding a password the system would
  refuse as too weak
- **THEN** the page reports the weakness and the account keeps the password it had

### Requirement: Decide the link before the password
The page SHALL decide whether the link is usable before considering the submitted entries at
all, so that a dead link is refused identically whatever was typed into the form.

#### Scenario: A dead link is refused rather than reporting a mismatch
- **WHEN** a link carrying an unrecognised, expired, used, or superseded code is submitted with
  two entries that differ
- **THEN** the page reports that the link cannot be used, in the same words as any other unusable
  link, and offers no password form

### Requirement: Never retain the confirmation entry
The second entry SHALL exist only to be compared against the first. It SHALL NOT be stored, in
any form, and SHALL NOT appear in any response.

#### Scenario: The confirmation is not stored
- **WHEN** a reset completes through the page
- **THEN** nothing recorded for that account holds the confirmation entry

#### Scenario: The confirmation is absent from every response
- **WHEN** the form is submitted, whether the reset completes or is refused
- **THEN** the response does not contain the text of either entry

### Requirement: Complete a reset through the API with a single password
The reset completion endpoint SHALL continue to accept a reset code and one new password, and
SHALL NOT require the password to be sent twice. Entering a password twice guards against a
person mistyping what they cannot see; it is not a security control, and requiring it of a
programmatic caller would test only that a value agrees with itself.

#### Scenario: A completion carrying one password still succeeds
- **WHEN** a completion is submitted with a valid code and a single acceptable new password, and
  no confirmation field
- **THEN** the request succeeds and the account authenticates with the new password
