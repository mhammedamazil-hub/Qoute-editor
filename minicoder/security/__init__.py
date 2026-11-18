"""Phase 5 security boundary: grants, policy, audit, and the tool guard."""

from __future__ import annotations

from minicoder.memory.db import BrainDB
from minicoder.security.guard import AuthorizationRequired, check_plan, check_tool, plan_is_mutating
from minicoder.security.service import (
    DENIED,
    AuthContext,
    AuthorizationDenied,
    SecurityService,
    Unauthenticated,
    internal_context,
    process_principal,
)

__all__ = [
    "AuthorizationRequired",
    "AuthorizationDenied",
    "Unauthenticated",
    "AuthContext",
    "DENIED",
    "SecurityService",
    "check_plan",
    "check_tool",
    "plan_is_mutating",
    "internal_context",
    "process_principal",
    "security",
    "service",
    "set_service",
]

_SERVICE: SecurityService | None = None


def security(db: BrainDB | None = None) -> SecurityService:
    """Process-wide security service bound to the active brain.

    Re-bound automatically when the active home changes so tests and CLI runs
    cannot accidentally issue grants against the wrong database.
    """
    global _SERVICE
    if db is not None:
        if _SERVICE is None or _SERVICE.db is not db:
            _SERVICE = SecurityService(db)
        return _SERVICE
    if _SERVICE is None:
        _SERVICE = SecurityService(BrainDB())
    return _SERVICE


def set_service(svc: SecurityService | None) -> None:
    global _SERVICE
    _SERVICE = svc


# Backwards-friendly alias: `service()` in the security package == the boundary.
service = security
