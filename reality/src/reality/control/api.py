"""Python API for the AI control layer (see API_REFERENCE.md).

Two calling styles, both going through ``operations.call``:

    from reality.control import api
    scene = api.call("scene.create", {"name": "demo"})
    text = api.call_json("scene.validate", json.dumps({"scene": scene}))   # JSON in, JSON out
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from . import operations
from .errors import OperationError


def call(name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run an operation. Raises ``OperationError`` on expected failures."""
    return operations.call(name, args)


def call_json(name: str, args_json: str) -> str:
    """JSON text in, JSON text out. Errors come back as ``{"error": {...}}`` instead of an exception."""
    try:
        args = json.loads(args_json) if args_json.strip() else {}
    except json.JSONDecodeError as exc:
        return json.dumps(OperationError("invalid_argument", f"arguments are not valid JSON: {exc}").to_dict(),
                          sort_keys=True)
    try:
        return json.dumps(operations.call(name, args), sort_keys=True, allow_nan=False)
    except OperationError as exc:
        return json.dumps(exc.to_dict(), sort_keys=True)


def operations_list() -> List[Dict[str, Any]]:
    """Name, description and input schema of every operation."""
    return operations.list_operations()
