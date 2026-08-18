# Conformance suite

Black-box checks that run against **any** learner's signup and signin, over HTTP, whatever
their specification decided.

19 checks: 10 for signup, 9 for signin.

## When to run it

**Once, at submission — after both change requests are folded in.**

Not earlier. The change requests add fields and behaviour, so a suite run mid-course would fail
work that is correct for that moment. Phase 9 is the point.

**Hold it back from learners.** Someone who has seen it builds to it instead of to their own
specification, which inverts the whole exercise.

## Why these particular checks

Every learner's specification differs — password minimums, status codes, what a successful
signin returns, what the terms-of-service field ended up being called. A suite asserting `400`
or `8 characters` would fail correct work.

So it asserts only what must be true of **any** defensible implementation, and takes the request
shapes from a payload you supply.

| Signup | Why it holds for everyone |
|---|---|
| Endpoint exists | It was the assignment |
| A valid payload succeeds | Any 2xx; the exact code is their choice |
| Duplicate email rejected | No defensible spec permits silent duplicates |
| Duplicate username rejected | Signup takes a username, so it has to mean something |
| Missing username rejected | The seed requirement names all three fields |
| Missing email rejected | Same |
| Missing password rejected | Same |
| Malformed email rejected | "Valid email" appears in every version |
| One-character password rejected | Below every plausible minimum |
| Password never echoed in a response | Universal, and the one people get wrong |

| Signin | Why it holds for everyone |
|---|---|
| Endpoint exists | It was the assignment |
| Correct credentials succeed | Any 2xx |
| Wrong password rejected | Universal |
| Unknown identifier rejected | Universal |
| Missing identifier rejected | Universal |
| Missing password rejected | Universal |
| **Signin by email succeeds** | Required by the email-signin change request |
| Password never echoed in a response | Universal |
| *Signin by username* | **Reported, not judged** — see below |

Rejections assert 4xx, successes assert 2xx. **Do not tighten these.** The moment the suite
encodes one learner's choices it starts failing correct work from another.

## The one check that reports instead of judging

After the email-signin change request, whether signin by **username** still works is a
backwards-compatibility decision the learner makes and records in their specification. Keeping it
is backwards compatible; dropping it for a general identifier field is a breaking change some
will defend well.

Both can be right, so the suite observes and reports. Run with `-rs` to see it:

```
SKIPPED — INFO: signin by username still works (HTTP 200) after the email-signin change
request. Check this against what their specification says about backwards compatibility.
```

Then check it against their spec. A learner who dropped username signin without saying so is the
finding; one who dropped it deliberately and documented it is not.

## Running it

The learner's server must be running. Take the payloads from **their specification** — including
any field a change request added, whatever they named it.

```bash
cd facilitator/conformance
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/pytest -v -rs \
  --base-url http://127.0.0.1:8000 \
  --signup-payload '{"username":"x","email":"x@example.com","password":"Str0ng-Passw0rd!","accepted_terms":true}' \
  --signin-payload '{"username":"x","password":"Str0ng-Passw0rd!"}'
```

The usernames and emails you pass are placeholders — the suite replaces them with fresh unique
values on every test, so runs never collide.

If they chose different paths or field names:

```bash
  --signup-path /api/auth/register/ \
  --signin-path /api/auth/login/ \
  --identifier-field identifier \
  --username-field user_name \
  --email-field email_address
```

`--identifier-field` is the one you will most often need: after the email-signin change request
some learners rename the signin field from `username` to something neutral.

## What this suite does NOT check, and where that lives instead

| Not here | Covered by |
|---|---|
| Password hashing and storage | Their own tests, and the lead at gate 2 — it is a requirement in their spec |
| The OpenAPI schema matching the spec | The learner in phase 5, and the lead at gate 2 |
| Whether tests verify what the spec says | `facilitator/review-prompt.md` |
| Anything about *how* it was built | The lead review |

This suite answers one question: **does signup and signin behave correctly?** Everything about
quality, traceability and whether the code matches the specification is a review job, not an
automated one.

## Reading the results

A failure is the start of a conversation, not a grade. Ask which requirement it maps to in their
specification, and which of the three cases it is — a code bug, a spec bug, or a gap where nobody
decided. That diagnosis is the skill the exercise exists to build.

A failure on **signin by email** almost always means one of two things: the change request was
never implemented, or it was implemented under a field name you have not passed as
`--identifier-field`. Check the second before raising the first.
