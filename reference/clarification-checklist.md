# Clarification checklist — signup

**Do not open this until you have written your own list.** Phase 3 asks you to find the
ambiguities in your specification yourself first. Reading someone else's list is not practice,
and the skill being trained is noticing that a requirement can be read two ways.

Once your own list is written, compare.

---

## What a complete signup specification has to settle
The ambiguities a complete signup specification must resolve:

1. Is the email address required? Is the username?
2. What makes an email valid — format checking, or delivery?
3. What are the rules for a username — length, allowed characters, reserved words?
4. Must usernames be unique? Are they case-sensitive?
5. What happens if one user's username is another user's email address?
3. Is the email case-sensitive for uniqueness? (`User@` vs `user@`)
4. Is whitespace trimmed from the email?
5. Is the password required?
6. What is the minimum password length? Is there a maximum?
7. Are there complexity rules, or only length?
8. Can the same email register twice?
9. What status and body come back when the email is already registered?
10. What status does invalid input return, and does the error identify the offending field?
11. What does a successful signup return — the user, a token, nothing?
12. Is the password ever included in a response? (Never.)
13. How is the password stored?
14. Is the account active immediately, or is confirmation required?

---

## How you did

**Ten or more found unaided is a strong first attempt.** Five or six is normal on a first pass.

The count matters far less than the *kind* of thing you missed. The most commonly overlooked are
case sensitivity, whitespace trimming, whether an account is active immediately, and the collision
between a username and someone else's email address — all cases where something exists in two
forms, or where a step was silently assumed.

Most people miss the same category twice. Knowing your own blind spot is the point of this
exercise, so write down which one was yours.
