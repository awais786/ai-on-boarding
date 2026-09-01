## Why

The page served at a reset link accepts a new password in a single field. A person who mistypes
it has no way to notice: the reset succeeds, the code is spent, and the account is now locked
behind a password nobody knows. Recovering means requesting another reset - if they work out
what happened at all, rather than concluding the reset is broken.

Every other place a password is chosen for the first time asks for it twice. The reset page is
the one place in this system where a person chooses a password they cannot verify, and it is
also the place where the cost of a typo is highest, because the account is already unreachable.

## What Changes

- The reset page asks for the new password twice and refuses to change anything unless both
  entries match.
- A mismatch keeps the form open, reports that the two entries differ, leaves the account's
  password as it was, and leaves the reset link still usable so the person can simply try again.
- A mismatch is reported ahead of any complaint about password strength. Someone who mistyped
  should be told about the typo, not given feedback on a password they did not mean to enter.
- The second entry exists only to be compared. It is never stored, in any form, and never
  appears in a response.
- The JSON completion endpoint is deliberately unchanged and continues to accept a single
  password. Not a breaking change, and not an oversight - see below.

Not **BREAKING**: no existing request shape changes. The reset page is a form rendered by this
system, so the added field ships with the form that submits it.

### Why the API is deliberately left alone

Confirming a password is a defence against a typo, not against an attacker. It protects a person
who cannot see what they typed. A programmatic caller composes its request from a value it
already holds, so requiring it to send that value twice adds a step that can only ever agree with
itself - ceremony that tests nothing.

The two entry points share a completion routine so that security guarantees - retiring a used
code, invalidating existing tokens - cannot hold for one and silently fail for the other. Those
are invariants an attacker could exploit if they diverged. Confirmation is not one of them:
nothing an attacker can do becomes easier because a JSON client sent one password instead of
two. The asymmetry is recorded as a requirement rather than left as an absence, so that a later
reader finds a decision instead of a gap.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-password-reset`: *Serve a page at the delivered link* changes - the page now asks for
  the new password twice, and completing the reset through it requires both entries to match.
  New requirements cover what a mismatch does, that a mismatch is reported before a strength
  complaint, that the second entry is never stored, and that the JSON endpoint still takes a
  single password.

## Impact

- The reset page and the template it renders. No change to either JSON endpoint, and no change
  to the shared completion routine both entry points call.
- No database change. The confirmation is compared and discarded; nothing about it is persisted,
  so there is no migration and no new column.
- No change to how codes are issued, expired, superseded, retired, or delivered, and no change
  to the identical-response guarantees that keep the reset path from revealing which addresses
  have accounts.
- Existing tests that submit the reset form need the second field added to their submissions.
