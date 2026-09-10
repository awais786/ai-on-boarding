"""A small, self-contained agent harness used to demonstrate runtime tool policy.

Three pieces, kept deliberately separate (see design.md in the change this shipped under):

- config.py    what capabilities the runtime permits (allowed_tools)
- tools.py     what each tool does, with no opinion on whether it's permitted
- dispatcher.py the single enforcement point: every tool call passes through here

Nothing is logged unless a handler is configured. `enable_verbose_logging()`
wires one up for devs who want to watch dispatch decisions go by.
"""
from __future__ import annotations

import logging

_VERBOSE_HANDLER_NAME = "harness-verbose"

logging.getLogger(__name__).addHandler(logging.NullHandler())


def enable_verbose_logging(level: int = logging.INFO, stream=None) -> logging.Handler:
    """Send harness dispatch decisions to stderr. Safe to call more than once."""
    logger = logging.getLogger(__name__)
    logger.setLevel(level)

    for existing in logger.handlers:
        if existing.name == _VERBOSE_HANDLER_NAME:
            existing.setLevel(level)
            return existing

    handler = logging.StreamHandler(stream)
    handler.name = _VERBOSE_HANDLER_NAME
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("[harness] %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return handler
