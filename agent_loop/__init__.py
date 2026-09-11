"""A model driving a loop with more than one tool available to it.

The model decides which tool it needs, the tool runs, its result re-enters the
conversation, and the model decides again with that result in hand - until it
reports it has finished. See openspec/specs/multi-tool-agent-loop/spec.md.
"""
