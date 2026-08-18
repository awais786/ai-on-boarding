# Glossary

Seven artefacts, and the difference between them is the whole exercise. If two of these blur
together in your head, come back here.

| Artefact | Answers | Written by | Changes when |
|---|---|---|---|
| **Constitution** | How do we build software on this project? | You, once | Engineering standards change |
| **Skill** | How do we perform a recurring task here? | You, refined over time | You learn a better way |
| **Specification** | What should this feature do? | You, with AI help | The product decision changes |
| **Clarification** | What did the specification leave ambiguous? | You | Ambiguity is found |
| **Plan** | How will we build it? | AI, from the spec | The technical approach changes |
| **Tasks** | What are the units of work? | AI, from the plan | The plan changes |
| **Code** | The implementation | AI, from the tasks | Any of the above changes |
| **Tests** | Executable proof the spec is satisfied | AI, from the spec | The spec changes |
| **Verification** | Does the implementation actually match the spec? | You | Every time you finish a task |

## The distinctions people get wrong

**Constitution vs skill.** The constitution is about *standards* — what must be true of any work
here ("every behavioural requirement must have automated verification"). A skill is about
*technique* — how a recurring job is done here ("generate migrations, never hand-write them;
validation goes in the serializer, not the view"). The constitution would still make sense if you
switched from Django to something else. The skill would not.

**Constitution vs specification.** The constitution is project-wide and outlives every
feature: *"every behavioural requirement must have automated verification."* The specification
is about one feature: *"a signup request with an email already in use is rejected."* If a
statement would still be true for a completely different feature, it belongs in the
constitution.

**Specification vs plan.** The specification says *what* — "duplicate emails are rejected".
The plan says *how* — "a unique constraint on the email column, surfaced as a 400 by the
serializer". If you find yourself naming a Django model, a serializer or a status code while
writing the specification, you have drifted into the plan.

**Plan vs tasks.** The plan is the shape of the solution. Tasks are the units of work that
build it. "Use DRF serializers for validation" is plan; "T002 — implement signup validation"
is a task.

**Task vs requirement.** A task is work to be done and is finished forever. A requirement is a
statement about behaviour and stays true for the life of the feature. `T003 — implement user
creation` is a task; *"a successful signup creates exactly one user"* is a requirement.

**Test vs verification.** A passing test tells you the code does what the test says. Verification
tells you the test says what the **specification** says. A green suite that tests the wrong
behaviour is the most expensive kind of wrong, because it looks like success.

**Why tests are written from the specification, not the code.** A test written by reading the
implementation tends to assert what the implementation does — it is shaped by the thing it is
supposed to judge, and it will pass forever while the software disagrees with its own
specification. Deriving the test from the requirement is what keeps it evidence rather than an
echo. Proving it can fail is what confirms you succeeded.

## Two words used precisely

**Instruction artefact** — anything a human edits to steer what gets built: the constitution,
the specification, and skills. Code and tests are *outputs*, produced from those. When output is
wrong, the fix belongs in whichever instruction artefact failed to prevent it.

**Ambiguity** — the specification can be read two ways. *"Passwords must be secure"* is
ambiguous; two developers will build different things and both will believe they complied.

**Gap** — the specification does not address the case at all. Nobody decided what happens
when `User@example.com` signs up after `user@example.com` already exists. A gap is not a bug
in the code, because the code was never told. It is a bug in the specification.
