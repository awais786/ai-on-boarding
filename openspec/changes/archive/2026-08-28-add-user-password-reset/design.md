## Context

See proposal.md - Why. `user-signup` (archived) established the account model: Django's built-in
`User`, email as the only identifier, `User.username` populated internally from the normalised
email. `add-user-signin` is planned but unimplemented; this change does not depend on it.

Two project constraints shape the approach: the project runs and tests with no environment
variables set, and `rest_framework.authtoken` is already installed and is where authentication
tokens live.

## Goals / Non-Goals

**Goals:**
- Satisfy every requirement in `specs/user-password-reset/spec.md`, in particular the two
  uniformity guarantees (identical answers to reset requests, identical refusals of bad codes)
  by construction rather than by remembering to keep branches in sync.

**Non-Goals:**
- No reset by SMS, security question, or support-desk override.
- No account lockout or notification-on-reset email to the account holder.
- No general-purpose rate limiting across the API. The limit added here is specific to the
  reset-request endpoint and exists to protect a named requirement; `add-user-signin` still owns
  failed-credential lockout, and the two are deliberately not wired together (see proposal.md -
  Sequencing).

## Decisions

**Store reset codes in a new model rather than using Django's stateless token generator.**
Django ships `PasswordResetTokenGenerator`, which derives a signed token from the user's primary
key, password hash, and last login, and needs no storage at all. It would satisfy the expiry
requirement (via the framework's reset-timeout setting) and would get single-use for free, since
changing the password changes the hash the token is derived from and every earlier token stops
validating.

It was rejected on one requirement: *Supersede an earlier unused code*. A stateless token has
nothing to revoke - two codes requested five minutes apart both stay valid until the password
actually changes, which is exactly what that requirement forbids. Satisfying it needs a record
per issued code that can be marked dead. Since the record has to exist for supersession, expiry
and single-use are tracked on it too rather than split across two mechanisms.

This is the project's second new model, after `SigninAttempt`. It is justified here rather than
allowed in silently, per the design rules.

**Supersession is a database invariant, not a sequence the view remembers to perform.** Issuing a
code means retiring the account's earlier one and inserting a new one - two statements, so two
concurrent requests can interleave and leave two rows usable, which is exactly what *Supersede an
earlier unused code* forbids. A partial unique index over the account, conditional on the row
still being usable, makes that state unrepresentable: the loser of the race raises
`IntegrityError` and retries, and its retry retires the winner's row before inserting its own, so
last-request-wins holds. This is the shape `user-signup` already uses for its duplicate-email
race, chosen over application-level locking for the same reason - the database is the only place
the invariant cannot be bypassed.

**Spending a code is a compare-and-swap, not a read followed by a write.** Resolving a code and
then marking it used leaves a window in which two completions both resolve the same code and both
proceed, breaking *Retire a reset code once it is used*. The obvious remedy, `select_for_update`,
is not available: this project runs on SQLite, which reports `has_select_for_update: False`, so
row locks are silently ignored and the guarantee would be untestable exactly where it is tested.
Instead the code is spent with a conditional `UPDATE ... WHERE usable` whose row count decides
the winner, which needs no locking and behaves the same on every backend. The completion runs
inside a transaction so the password write, the spend, and the token deletion commit together.

**Store a hash of the reset code, never the code itself.** The stored record holds the account,
the issue time, a used/superseded marker, and a digest of the code - not the code. A read of the
database therefore does not hand over working reset codes, matching the treatment signup already
gives passwords (*Store a new password unrecoverably*). Verification hashes the submitted code
and compares digests. Alternative considered: store the code in the clear, which is simpler and
was rejected because it makes the reset table itself a credential store.

**Generate codes from `secrets.token_urlsafe`, not from a counter or a UUID.** The code is the
only thing standing between an attacker and an account, so it needs to be unguessable rather
than merely unique. A UUID is unique but its generation is not required to be unpredictable.

**One fixed refusal path for every unusable code.** *Reject every bad code identically* names
four distinct causes - unrecognised, expired, used, superseded. The view resolves a submitted
code to "usable record or nothing" in a single step and has exactly one refusal branch, so the
four cases cannot drift apart. The alternative - four checks, each with its own error return -
is the duplication the requirement exists to prevent, and is rejected for the same reason
`add-user-signin` rejected hand-rolled credential comparison.

**The reset-request endpoint always does the same visible thing.** It validates the email's
shape, looks the account up, issues and sends a code only if one exists, and returns the same
fixed 200 body either way. *Answer every reset request identically* is then a property of there
being a single return statement, not of two branches being kept in agreement.

The lookup is case-insensitive. Signup lowercases what it stores, so a lowercase match would be
enough for accounts it created - but accounts made through `createsuperuser`, the admin, or a
shell keep whatever case they were given, and their holders are equally entitled to a reset.
Matching case-insensitively is what *Deliver a reset code to a registered address* means by
"registered"; an exact match would silently answer 200 and send nothing.

**Issuing and sending are one transaction, so a failed delivery undoes the issuance.** Issuing a
code retires the account's previous one, and that happens before the send can possibly succeed.
Left alone, a mail server being down destroyed the link already sitting in someone's inbox and
supplied no replacement - the account became unable to complete a reset at all, and the 200 said
nothing was wrong. Wrapping issue-and-send in one transaction means a delivery failure rolls the
issuance back: the earlier code is still usable and no orphan row is left behind, which is what
*Leave earlier codes usable when delivery fails* asks for. Alternative considered: send first and
supersede afterwards, which is impossible - the message has to carry the new code.

**The reset-request endpoint is limited per email address, not per caller.** *Limit how often a
reset may be requested for one address* exists because every request supersedes the previous
code, so an unauthenticated caller looping on someone else's address could keep that person
permanently unable to finish a reset, and mail-bomb them on the way. Limiting by client address
would not fix it: the harm is done to the account, not by a particular caller, and a distributed
caller would walk straight through. Limiting by the submitted address caps the churn at its
target, and combined with the transaction above it means the code a person already holds
survives a flood.

The limit is applied to the address as submitted, whether or not an account exists for it, so
being limited reveals nothing about who has an account - the same reason `SigninAttempt` is keyed
on the submitted email rather than on a found account.

**A refused request gets a fixed body, not the framework's default.** DRF's throttled response
appends the wait remaining, rounded up: `Expected available in 3595 seconds.` Two refusals a
second apart therefore differ by one, which quietly breaks *Limit how often a reset may be
requested for one address* - its refusals are required to be identical in status and body, and
the surrounding uniformity requirements are built on byte-identity rather than on status alone.
The countdown is dropped and the body fixed, so the guarantee holds literally and a test of it
can assert equality outright instead of tolerating a drift. Cost accepted: a legitimate client
loses the retry-after hint, which this project has no client relying on. Alternative considered:
scoping the guarantee to status only, rejected because it would leave two different meanings of
"identical" in one spec.

**Nothing on the registered-only branch may raise.** A single return statement is not enough on
its own: issuing a code and sending mail happen only when an account exists, so an exception in
either answers a registered address with a 500 while an unregistered one still gets 200. That
difference is an enumeration oracle against *Answer every reset request identically*, reachable
by nothing more exotic than a mail server being down. The whole branch is therefore wrapped, and
the guard is deliberately broad - there is no exception type worth letting through, because any
of them would be visible to the caller. Failures are logged rather than swallowed silently, so a
broken configuration is still discoverable by whoever runs the service. The cost is accepted: a
delivery failure retires the account's previous code without supplying a working replacement,
and the holder must request another reset.

**Reuse signup's password validator rather than restating the rules.** *Hold a new password to
the signup strength rules* is a statement about sameness, so the implementation shares the one
validator that signup already applies. Restating the thresholds in a second place would let the
two drift, and the requirement would then be silently false.

**Invalidate authentication tokens by deleting the account's token rows on success.**
`rest_framework.authtoken` issues at most one token per user and offers no revocation API beyond
deleting the row, so deletion is the mechanism. This satisfies *Invalidate existing
authentication tokens on reset* and is testable today, before signin exists, because it acts on
the stored token rather than on the signin endpoint.

**Build the reset link from an explicit base-URL setting, never from the incoming request.**
*Deliver the reset link as an absolute address* needs a scheme and host from somewhere. The
obvious candidate is `build_absolute_uri`, which takes them from the request that asked for the
reset and so needs nothing configured - and it is rejected, because that request is made by
whoever wants the reset, not by the account holder. Password reset is the textbook target for
host-header poisoning: an attacker submits the victim's address with a forged `Host`, the victim
receives a genuine reset mail pointing at the attacker's server, follows it, and surrenders a
working code. The account falls without the attacker ever reaching the victim's inbox.

`ALLOWED_HOSTS` is the only check on that, which would make the safety of this flow a side effect
of a setting kept for an unrelated reason - and this project ships with it empty. A module-level
base URL in settings is not attacker-controllable, needs no environment variable, and fails
visibly: a value that does not match the deployment produces dead links somebody reports, rather
than working links pointing somewhere they should not. It also makes the requirement testable
against a known prefix instead of against whatever host a test client happened to send.

Also considered and rejected: `django.contrib.sites`, which costs a migration and a fixture row
to hold one string, and still has to be kept in step with the deployment by hand.

**Serve the reset page with a server-rendered form, and share one completion routine with the
API.** *Serve a page at the delivered link* needs something to answer a browser at the address
the mail carries. Two ways were considered.

A page of JavaScript that `fetch`es the existing JSON endpoint keeps the server dumb, but makes
the reset flow depend on scripting for what is a two-field form, and leaves the page unable to
say anything useful when scripting is off. Rejected.

A plain Django view rendering a template was chosen instead: it works in any browser, needs no
new dependency, and reuses the template engine already configured with `APP_DIRS`. Its POST
handler and the API view both call one `complete_reset` routine, so "Retire a reset code once it
is used", "Invalidate existing authentication tokens on reset" and the password write happen in
exactly one place. Two entry points, one implementation - a second copy of that sequence is
precisely the drift the uniformity requirements exist to prevent.

The page lives outside `/api/` because the mail carries a human-facing address, not an API route,
and it is deliberately not part of the OpenAPI schema: it is a page, not an endpoint.

**Send mail through Django's email framework, with a backend that needs no configuration.**
Development uses the console backend and tests use the locally-held backend, so *Deliver a reset
code to a registered address* and *Deliver nothing to an unregistered address* are both assertable
against the in-memory outbox without a mail server and without the environment variables the
project has so far avoided. Choosing a real SMTP backend is a deployment concern, not a change to
any requirement here.

## Risks / Trade-offs

- [A second new model, and a second migration] → justified above against a genuinely simpler
  stateless alternative, and traced to the single requirement that rules the alternative out.
- [A base URL that does not match the deployment produces links that go nowhere] → the accepted
  cost of not deriving the host from the request. The failure is loud and reported by the first
  person who follows a link, where the rejected alternative fails silently and in the attacker's
  favour. A deployment checklist entry, not a design problem.
- [Reset code rows accumulate, one per request, with no expiry sweep] → the same unbounded-growth
  trade-off `add-user-signin` accepted for `SigninAttempt`. Recorded here rather than discovered
  later; a periodic purge of used and expired rows is the obvious remedy if it ever matters.
- [The reset-request endpoint is a free outbound-mail trigger for any address that has an
  account] → capped by the per-address limit above. An attacker can still cause some mail, and
  can still consume a person's own allowance for the period, but can no longer keep them from
  finishing a reset: the code already delivered survives, because a limited request never reaches
  the issuing step.
- [The limit is counted in Django's cache, which this project has not configured beyond the
  process-local default] → counts are therefore per worker process, so the effective limit under
  several workers is the configured one multiplied by the worker count. Chosen anyway: it is the
  idiomatic mechanism, it needs no new table, and the requirement it protects is about stopping
  unbounded churn rather than about an exact number. `SigninAttempt` took the opposite decision
  for lockout, where the exact count is the requirement - the divergence is deliberate and worth
  revisiting if the two ever merge.
- [Mail is sent while the transaction that issued the code is still open] → the insert and the
  supersede take SQLite's write lock, and it is then held for as long as the send takes. With the
  console backend configured here that is microseconds and invisible; against a real SMTP server
  it is a network round-trip, during which every other write - a signup, another reset - blocks
  and then fails with `database is locked` once the driver's timeout expires. There is a second
  edge: the message can leave before the commit, so a commit that then fails hands the recipient
  a link to a code that does not exist. Accepted for now because the alternative - commit the
  issuance, send, then retire the new code and restore the previous one on failure - replaces one
  atomic step with a compensating one that can itself fail, and *Leave earlier codes usable when
  delivery fails* currently rests on the rollback being free. Revisit before a real mail backend
  is configured; that is the point at which the trade stops being free.
- [Two accounts can hold the same email address, and only the lowest-numbered one can ever reset]
  → `User.email` carries no uniqueness constraint and only `SignupSerializer` normalises and
  de-duplicates, so accounts made by `createsuperuser`, the admin, or a shell can collide. The
  lookup is ordered by primary key for determinism, which means the same holder is chosen every
  time and the others are permanently unable to reset - while still receiving the uniform 200
  that says a link was sent. Recorded rather than fixed: refusing the request would need a
  response that differs from the uniform one, and mailing every match would let anyone who
  registers a colliding address receive somebody else's reset link. The real remedy is a
  uniqueness constraint on the column, which belongs to a change of its own.
- [Timing may distinguish a registered from an unregistered address on the request endpoint,
  since only one of them hashes and sends] → the spec's uniformity requirement is scoped to the
  response, as signin's is. Noted so that a later decision to close the timing channel is a
  deliberate change with a requirement behind it, not a silent one.
