"""A small JSON-Schema subset checker (stdlib only).

Supported keywords: type, properties, required, items, enum, minimum, maximum, minItems, maxItems,
additionalProperties (boolean). The same schemas are published as MCP ``inputSchema`` and used for
CLI help, so the three interfaces check arguments identically.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from .errors import OperationError

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _check(value: Any, schema: Dict[str, Any], path: str, errors: List[str]) -> None:
    label = path or "value"
    t = schema.get("type")
    if t is not None:
        if t == "number":
            ok = _is_number(value)
        elif t == "integer":
            ok = isinstance(value, int) and not isinstance(value, bool)
        else:
            ok = isinstance(value, _TYPES[t])
        if not ok:
            errors.append(f"{label} must be of type {t}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{label} must be one of {schema['enum']}")
    if t in ("number", "integer"):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{label} must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{label} must be <= {schema['maximum']}")
    if t == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{label} needs at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{label} allows at most {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                _check(item, schema["items"], f"{path}[{i}]", errors)
    if t == "object":
        props = schema.get("properties", {})
        prefix = (path + ".") if path else ""
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{prefix}{key} is required")
        for key, sub in value.items():
            if key in props:
                _check(sub, props[key], prefix + key, errors)
            elif schema.get("additionalProperties", True) is False:
                errors.append(f"unknown argument {prefix}{key}")


def validate_args(args: Dict[str, Any], schema: Dict[str, Any], operation: str) -> None:
    """Raise ``OperationError(invalid_argument)`` listing every problem at once."""
    errors: List[str] = []
    _check(args, schema, "", errors)
    if errors:
        raise OperationError("invalid_argument", f"{operation}: " + "; ".join(errors),
                             {"operation": operation, "problems": errors})
