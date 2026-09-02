"""Ensures `agent_loop/agent_loop.py` and `agent_loop/enhanced_agent_loop.py` are importable as
top-level modules (`import agent_loop`, `import enhanced_agent_loop`) during test collection.

Both scripts live in the `agent_loop/` folder as siblings, not a Python package (no
`__init__.py`), so their folder - not the repo root - must be on `sys.path`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "agent_loop"))
