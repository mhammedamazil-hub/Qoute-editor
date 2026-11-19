"""Stable error type shared by the CLI, the Python API and the MCP adapter."""

from __future__ import annotations

from typing import Any, Dict, Optional

# Codes are part of the public interface. Do not rename them without a schema-version bump.
ERROR_CODES = (
    "invalid_argument",  # a call argument has the wrong type, range or value
    "schema_error",      # a scene or result document does not satisfy its schema
    "unsupported",       # valid input that this release does not implement
    "resource_limit",    # a step, record, memory, time or pixel budget was exceeded
    "invalid_state",     # the simulation reached a non-physical state and stopped
    "cancelled",         # the caller cancelled the operation
    "not_found",         # a named body, plane, material or operation does not exist
)


class OperationError(Exception):
    """An operation failed in a way the caller should see and can act on."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def to_dict(self) -> Dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}
