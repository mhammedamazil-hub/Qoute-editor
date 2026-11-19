"""AI control layer for PROJECT REALITY: one operation registry behind the CLI, the Python API and the MCP adapter.

Start with ``AI_CONTROL_ARCHITECTURE.md``. Minimal use from Python::

    from reality.control import call
    scene = call("scene.create", {"name": "demo"})

All operations take and return JSON-compatible dictionaries. Expected failures raise ``OperationError``.
"""

from .errors import OperationError
from .operations import call, list_operations

__all__ = ["OperationError", "call", "list_operations"]
