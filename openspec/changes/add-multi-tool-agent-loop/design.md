## Context

See proposal.md - Why. The requirements this design satisfies are in
`specs/multi-tool-agent-loop/spec.md`.

Two constraints shape everything below. First, the loop is the deliverable, not a means to one:
the value is in the control flow being written out explicitly. Second, only one requirement -
*Let the model choose the tool* - needs a live model to verify; the rest are properties of the
loop and must be verifiable by anyone, on any machine, with no credential.

The behaviour of a live model was observed directly while preparing this design. Those
observations are recorded under Decisions where they justify a choice, because several of them
contradict what a reasonable person would assume from the requirements alone.

## Goals / Non-Goals

**Goals:**

- The loop's control flow is readable in one place, and the termination decision is a single,
  obvious read of the model's stop signal.
- Every requirement except *Let the model choose the tool* is verifiable with no credential.
- A run that gives up is impossible to confuse with a run that finished.

**Non-Goals:**

- Streaming, retries, or a general-purpose agent framework. Nothing in the spec asks for them.
- Concurrent execution of tools requested together. The spec requires only that their results are
  returned in one turn, not that they run in parallel.
- Any use in, or coupling to, the Django project.

## Decisions

### The loop is written out, not delegated to the SDK's tool runner

The Anthropic SDK ships a tool runner that performs this whole cycle. It is the right choice for
production code and the wrong one here: the capability being specified *is* the cycle, and a
delegated loop cannot demonstrate the requirement *Terminate only on the model's reported stop
reason*, because the termination decision would be inside the library. It is also a beta
interface. Rejected in favour of an explicit loop.

### Termination reads the stop reason, and nothing else

Satisfies *Terminate only on the model's reported stop reason*. The loop branches on the stop
reason alone: the "requesting a tool" value executes tools and continues, the "finished" value
returns, and **every other value is reported and stops the run** - satisfying *Report a response
the loop cannot act on*.

That last branch is not defensive padding. The first live request made while preparing this
design returned the stop reason `max_tokens`, because the model's reasoning consumed the token
budget before any text was produced. A loop handling only the two expected values would have
fallen through it silently and returned nothing as though that were an answer.

The same observation rules out the alternatives the issue forbids, and shows why: in that
response the first content block was a reasoning block, not text, and in every live run of the
default model the first block was explanatory text *while the model was requesting a tool*.
Either check would have given the wrong answer on a real response.

### The model's response is appended whole, never reconstructed

Satisfies *Thread results back into the conversation*. The loop appends the response's content
exactly as received rather than extracting the parts it recognises.

This is required, not merely tidy. A live response was observed carrying a reasoning block
alongside the tool request; that block must be returned unchanged in the next request, and
rebuilding the turn from the parts the loop understands would silently discard it. Appending the
whole response also keeps each tool request paired with the result answering it, which the API
requires.

### A tool request carrying no tool is an anomaly, not an empty turn

Satisfies *Report a response the loop cannot act on*. If the stop reason says a tool was
requested but no tool request is present, the loop stops and records it.

Observed while preparing this design: sending back a turn with no results in it is rejected
outright, and a loop that builds its results list without checking it is non-empty will
eventually do exactly that. Stopping with a named anomaly is better than an error from the far
end of the wire that says nothing about the cause.

### Reaching the cap raises

Satisfies *Cap the number of iterations for safety*. On the 20th iteration without completion the
loop logs a warning and raises a dedicated error.

The alternatives were returning `None` and returning a result object carrying a "completed" flag.
Both were rejected for the same reason: they let a caller who does not check receive a
gave-up run as though it were a finished one. That is the precise confusion between "looks
finished" and "reported finished" that this whole capability exists to teach, so the design
should not reintroduce it at the boundary.

### The calculator parses and walks the expression rather than evaluating it

Satisfies *Evaluate expressions without executing arbitrary code*. The expression is parsed into a
syntax tree and walked, permitting only numeric literals, the arithmetic operators, and
parentheses; anything else is refused before any evaluation happens.

`eval` with a restricted namespace was rejected: the input is a string chosen by a model, the
restriction is difficult to prove complete, and a failure is arbitrary code execution. A parsing
dependency was rejected as disproportionate for four operators. Refusal is a returned error
result, not an exception, so a refused expression is something the model can respond to.

### A power is refused when its result would be enormous, predicted rather than attempted

Satisfies *Refuse an expression whose result would be too large to compute*. Before a power is
evaluated, the size of its result is predicted from the base's bit length and the exponent; above
a fixed bound the expression is refused and nothing is computed.

This requirement was added during implementation rather than written up front. The whitelist
above admits `2 ** 999999999` - it is arithmetic, it reaches nothing, and its result is not
non-finite; it simply never returns. That is reachable in a normal run, because the expression is
chosen by the model, so refusing arbitrary code without also bounding the work left a tool that
could still hang the loop.

Prediction was chosen over the alternatives because both of those fail on the case that matters.
A timeout would have to let the computation start, and by then the memory is already being
claimed. A cap on the exponent alone is defeated by nesting - `(10**1000) ** 1000` keeps every
exponent small while the result grows without limit - whereas predicting from the base's actual
bit length is checked afresh at each level and so bounds the nested case too. Floats are left to
the existing non-finite check, which already catches them.

### The client is supplied to the loop; the tools are not

The loop takes the model client as an argument, so the tests can supply a stub that returns
scripted responses. The tool set stays a module-level constant, because nothing requires it to
vary - the tests exercise the loop by controlling what the model *asks for*, not by changing what
is on offer.

### The default model is the cheapest one measured to complete the task

`claude-haiku-4-5`, overridable with `AGENT_LOOP_MODEL`.

It was measured completing the full multi-tool lifecycle three times out of three, choosing
`web_search` before `calculator` unprompted each time. It is roughly five times cheaper than the
Opus-tier alternative, which was measured completing the same task four times out of four. The
effort parameter is **not** sent: the API rejects it on this model outright, and reasoning is off
by default there, so the cheap behaviour needs no configuration.

### Verification is a stub client, plus one live check that announces its own absence

Satisfies *Demonstrate the complete lifecycle against a live model*. A stub client returning
scripted responses covers every requirement except *Let the model choose the tool*, needs no
credential, and is deterministic. One further check drives a live model end to end.

When no credential is present that check does not run - but the run **says so**, naming the
requirement left unverified. Silently omitting it was rejected: a suite that reports success
having quietly stopped checking something is worse than one that never checked it, because the
green result is read as evidence.

### A standalone package with its own dependency list

The Anthropic SDK is a new dependency and is confined to this package, which has its own
requirements file and virtual environment. The Django project gains no dependency, and its test
suite is untouched. The capability has no HTTP surface and no database, so there is nothing to
gain from placing it inside a Django application.

## Risks / Trade-offs

**The live check depends on a model's judgement, so it could become flaky.** → It asserts the
*sequence of tool names* and that the run completes, not the wording of the answer. The default
model was measured at three of three, and the model is overridable without a code change if that
proves insufficient.

**The stub encodes our reading of the API, so a misreading would be invisible to it.** → This is
the real limit of credential-free testing: a stub cannot contradict the assumption that built it.
Mitigated by the live check, and by the observations recorded above, each of which came from a
real response rather than from the documentation.

**With the default model, the live check does not exercise the reasoning-block path**, because
that model produces none. → The requirement to preserve a response whole was verified directly
against a reasoning-enabled model while preparing this design, and that model remains selectable
through `AGENT_LOOP_MODEL`. Recorded here so the gap is known rather than assumed away.

**One unexplained rejection was seen during preparation** - a turn refused as having empty
content - which did not reproduce across four subsequent runs. → Its immediate cause is
understood and is designed against (see the anomaly decision above); it is recorded rather than
explained away, because the underlying trigger was never reproduced.

**Every live run costs money.** → Cents at this scale, and the credential-free suite is what
gates the change; the live check is additional evidence rather than the primary gate.
