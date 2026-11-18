"""The last line of defence: every tool execution is checked here.

`EditorBridge.call` invokes :func:`check_tool` immediately before it writes to
the editor's stdin.  That placement is the point of the Phase 5 remediation: the
check is not in the router, not in the planner and not in the UI, so a new
endpoint, a script or an internal helper cannot reach the editor without it.

Three properties are enforced:

* an **unknown tool** is rejected (fail closed) even though the bridge might
  happily execute it;
* a **mutating tool** requires a real :class:`AuthContext` — no default, no
  environment flag, no request body boolean;
* a grant context must match the tool **exactly** (``editor.tool``) or belong to
  the instruction the grant was minted for (``editor.instruction``).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from minicoder.security import policy
from minicoder.security.service import AuthContext


class AuthorizationRequired(PermissionError):
    """A tool call was refused because no valid authority backed it."""

    def __init__(self, tool: str, reason: str, tool_class: str | None = None) -> None:
        self.tool = tool
        self.reason = reason
        self.tool_class = tool_class
        super().__init__(f"{tool}: {reason}")

    def to_json(self) -> dict[str, Any]:
        return {"tool": self.tool, "reason": self.reason, "tool_class": self.tool_class}


def check_tool(tool: str, args: dict[str, Any] | None, ctx: AuthContext | None) -> None:
    """Raise `AuthorizationRequired` unless ``ctx`` may run ``tool``."""
    cls = policy.classify_tool(tool)
    if cls is None:
        raise AuthorizationRequired(tool, "unknown tool is not in the policy table")
    if cls is policy.ToolClass.READ_ONLY:
        return
    if ctx is None:
        raise AuthorizationRequired(tool, "no authorization context", cls.value)
    if ctx.kind == "internal":
        # In-process code.  Explicit, attributed to the OS user, and audited by
        # whichever operator action started it.
        return
    if ctx.kind != "grant":
        raise AuthorizationRequired(tool, "context carries no authority", cls.value)
    if ctx.action == policy.ACTION_TOOL and ctx.scope == tool:
        return
    if ctx.action == policy.ACTION_INSTRUCTION:
        if ctx.allowed_tools is None or tool in ctx.allowed_tools:
            return
        raise AuthorizationRequired(tool, "tool is not part of the authorized plan", cls.value)
    raise AuthorizationRequired(
        tool, f"grant action {ctx.action!r} does not authorize a tool call", cls.value
    )


def check_plan(planned: Iterable[dict[str, Any]], ctx: AuthContext | None) -> None:
    """Authorize a whole plan *before* its first step executes.

    Checking the plan up front means a request is either fully authorized or
    rejected with nothing executed — no half-applied canvas.
    """
    for step in planned:
        tool = str(step.get("tool", ""))
        check_tool(tool, step.get("args") or {}, ctx)


def plan_is_mutating(planned: Iterable[dict[str, Any]]) -> bool:
    return any(policy.is_mutating(str(step.get("tool", ""))) for step in planned)
