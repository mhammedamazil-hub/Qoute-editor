"""The authorization boundary.

One service decides, one context object carries the decision, and the editor
bridge re-checks the context immediately before it executes a tool.  Nothing in
this module trusts a boolean from a request body.

Flow for a consequential API call::

    security.authenticate(bearer)          -> principal | None
    security.issue_grant(...)              -> grant (operator only)
    security.authorize_execution(grant...) -> AuthContext   [grant consumed + audited]
    agent.execute(..., auth=ctx)           -> bridge.call(tool, auth=ctx)  [re-checked]
    security.finish(ctx, ok=...)           -> executed | failed  [+ audited]

If any step fails the operation does not run.  If the audit row cannot be
written, the operation does not run either (fail closed, see `authorize_execution`).
"""

from __future__ import annotations

import getpass
import hmac
from dataclasses import dataclass, field
from typing import Any, Literal

from minicoder.memory.db import BrainDB
from minicoder.security import policy
from minicoder.security.audit import (
    DECISION_AUTHORIZED,
    DECISION_EXECUTED,
    DECISION_FAILED,
    DECISION_REJECTED,
    DECISION_REQUESTED,
    SecurityAudit,
)
from minicoder.security.grants import (
    DEFAULT_TTL,
    DESTRUCTIVE_TTL,
    Grant,
    GrantError,
    GrantStore,
    operator_token,
    principal_fingerprint,
)

AuthKind = Literal["grant", "internal", "denied"]


class AuthorizationDenied(PermissionError):
    """A consequential operation was not authorized.  Always deny-closed."""

    def __init__(self, code: str, detail: str = "", *, status: int = 403,
                 requires: dict[str, Any] | None = None) -> None:
        self.code = code
        self.detail = detail
        self.status = status
        # What the client would have to ask for, so the refusal is actionable.
        self.requires = requires or {}
        super().__init__(f"{code}: {detail}" if detail else code)

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail, "requires_grant": self.requires}


class Unauthenticated(AuthorizationDenied):
    def __init__(self, detail: str = "operator token required") -> None:
        super().__init__("unauthenticated", detail, status=401)


@dataclass(frozen=True)
class AuthContext:
    """The authority a single operation runs under.

    ``kind='grant'`` means a real, validated, consumed grant backs this call.
    ``kind='internal'`` means code running inside the operator's own process
    (CLI, sleep worker, tests) — an explicit, auditable decision, not a bypass.
    ``kind='denied'`` carries no authority at all.
    """

    kind: AuthKind
    principal: str
    action: str = ""
    scope: str = ""
    resource: str = ""
    grant_id: str = ""
    request_id: str = ""
    purpose: str = ""
    allowed_tools: frozenset[str] | None = None
    instruction: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def authorized(self) -> bool:
        return self.kind in ("grant", "internal")

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "principal": self.principal,
            "action": self.action,
            "resource": self.resource,
            "grant_id": self.grant_id,
            "request_id": self.request_id,
        }


DENIED = AuthContext(kind="denied", principal="anonymous")


def process_principal() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover - exotic environments
        user = "unknown"
    return f"process:{user}"


def internal_context(purpose: str, *, request_id: str = "", meta: dict[str, Any] | None = None) -> AuthContext:
    """Authority for code running inside the operator's process.

    Used by the learning/sleep pipelines and by tests.  It is *not* reachable
    from an HTTP request that has not already validated a grant: the API builds
    one only after consuming one.
    """
    return AuthContext(
        kind="internal",
        principal=process_principal(),
        action="internal",
        scope=purpose,
        purpose=purpose,
        request_id=request_id,
        allowed_tools=None,
        meta=meta or {},
    )


class SecurityService:
    def __init__(self, db: BrainDB) -> None:
        self.db = db
        self.audit = SecurityAudit(db)
        self.grants = GrantStore(db)

    # ----------------------------------------------------------- principals
    def operator_token(self) -> str:
        """The local operator capability token (0600 file, never in the repo)."""
        return operator_token()

    def authenticate(self, raw_token: str | None) -> str | None:
        """Map a bearer token to a principal fingerprint, or ``None``."""
        if not raw_token:
            return None
        expected = operator_token()
        if hmac.compare_digest(raw_token.strip(), expected):
            return principal_fingerprint(expected)
        return None

    def require_operator(self, raw_token: str | None, *, request_id: str, action: str) -> str:
        principal = self.authenticate(raw_token)
        if principal is None:
            self.audit.record_tx(
                request_id=request_id,
                principal="anonymous",
                action=action,
                resource="security",
                decision=DECISION_REJECTED,
                result="denied",
                reason="missing or invalid operator token",
            )
            raise Unauthenticated()
        return principal

    # --------------------------------------------------------------- grants
    def issue_grant(
        self,
        raw_token: str | None,
        *,
        action: str,
        resource: str | None = None,
        scope: str = "",
        ttl: int | None = None,
        request_id: str = "",
        reason: str = "",
    ) -> Grant:
        principal = self.require_operator(raw_token, request_id=request_id, action=f"grant.issue:{action}")
        if action not in policy.GRANTABLE_ACTIONS:
            raise AuthorizationDenied("unknown_action", f"{action!r} cannot be granted")
        resource = resource or policy.resource_for(action)
        if ttl is None:
            ttl = DESTRUCTIVE_TTL if action in (policy.ACTION_TOOL, policy.ACTION_INSTRUCTION) else DEFAULT_TTL
        try:
            grant = self.grants.issue(
                principal=principal,
                action=action,
                resource=resource,
                scope=scope,
                ttl=ttl,
                request_id=request_id,
                meta={"reason": reason} if reason else None,
            )
        except GrantError as exc:
            raise AuthorizationDenied(exc.code, exc.detail) from exc
        self.audit.record_tx(
            request_id=request_id,
            principal=principal,
            action=f"grant.issue:{action}",
            resource=resource,
            decision=DECISION_AUTHORIZED,
            grant_id=grant.id,
            result="issued",
            reason=reason,
            correlation={"scope": scope, "ttl": ttl},
        )
        return grant

    # ---------------------------------------------------------- enforcement
    def authorize_execution(
        self,
        *,
        grant_id: str,
        principal: str | None,
        action: str,
        resource: str,
        scope: str = "",
        request_id: str = "",
        instruction: str = "",
        allowed_tools: frozenset[str] | None = None,
    ) -> AuthContext:
        """Consume a grant and return the context the operation runs under.

        Order matters and is deliberate: the grant is consumed *before* the
        audit row is written, both inside the same ``BEGIN IMMEDIATE``
        transaction.  If the audit write fails the transaction rolls back — the
        grant stays unconsumed and nothing executes.
        """
        from minicoder.security.audit import DECISION_REPLAYED

        if not grant_id:
            self.audit.record_tx(
                request_id=request_id,
                principal=principal or "anonymous",
                action=action,
                resource=resource,
                decision=DECISION_REJECTED,
                result="denied",
                reason="no grant supplied",
                correlation={"scope": scope},
            )
            raise AuthorizationDenied(
                "missing_grant",
                "this operation requires an authorization grant for "
                f"{action} on {resource}",
                requires={"action": action, "resource": resource, "scope": scope},
            )
        if not principal:
            self.audit.record_tx(
                request_id=request_id,
                principal="anonymous",
                action=action,
                resource=resource,
                decision=DECISION_REJECTED,
                grant_id=grant_id,
                result="denied",
                reason="grant presented without an authenticated principal",
            )
            raise Unauthenticated("a grant must be presented with the operator token")

        # One transaction: consume + audit.  A failure in either leaves neither.
        try:
            with self.db.write() as conn:
                row = conn.execute("SELECT * FROM auth_grants WHERE id=?", (grant_id,)).fetchone()
                if not row:
                    raise GrantError("unknown_grant", "no such grant")
                g = self.grants.get(grant_id)
                assert g is not None
                self.grants._verify_signature(g)
                self.grants.check_scope(
                    g, principal=principal, action=action, resource=resource, scope=scope
                )
                if g.outcome == "revoked":
                    raise GrantError("revoked", "grant was revoked")
                if g.consumed_at:
                    raise GrantError("replayed", f"consumed at {g.consumed_at}")
                from minicoder.memory.db import utcnow

                now = utcnow()
                if g.expires_at <= now:
                    raise GrantError("expired", f"expired at {g.expires_at}")
                cur = conn.execute(
                    "UPDATE auth_grants SET consumed_at=?, consumed_by=?, outcome='consumed'"
                    " WHERE id=? AND consumed_at IS NULL",
                    (now, request_id, grant_id),
                )
                if cur.rowcount != 1:  # pragma: no cover - serialised by BEGIN IMMEDIATE
                    raise GrantError("replayed", "lost the race for this grant")
                self.audit.record(
                    conn,
                    request_id=request_id,
                    principal=principal,
                    action=action,
                    resource=resource,
                    decision=DECISION_AUTHORIZED,
                    grant_id=grant_id,
                    result="authorized",
                    correlation={"scope": scope, "instruction": bool(instruction)},
                )
        except GrantError as exc:
            decision = DECISION_REPLAYED if exc.code == "replayed" else DECISION_REJECTED
            self.audit.record_tx(
                request_id=request_id,
                principal=principal,
                action=action,
                resource=resource,
                decision=decision,
                grant_id=grant_id,
                result="denied",
                reason=f"{exc.code}: {exc.detail}",
                correlation={"scope": scope},
            )
            status = 409 if exc.code == "replayed" else 403
            raise AuthorizationDenied(exc.code, exc.detail, status=status) from exc
        except Exception as exc:
            # Any failure to record the authorization — integrity error, locked
            # database, disk full — means the operation must not run.  Fail closed.
            raise AuthorizationDenied(
                "audit_unavailable", f"refusing to execute without an audit record: {exc}", status=503
            ) from exc

        return AuthContext(
            kind="grant",
            principal=principal,
            action=action,
            scope=scope,
            resource=resource,
            grant_id=grant_id,
            request_id=request_id,
            instruction=instruction,
            allowed_tools=allowed_tools,
        )

    def requested(
        self,
        *,
        request_id: str,
        principal: str,
        action: str,
        resource: str,
        correlation: dict[str, Any] | None = None,
    ) -> None:
        self.audit.record_tx(
            request_id=request_id,
            principal=principal,
            action=action,
            resource=resource,
            decision=DECISION_REQUESTED,
            correlation=correlation or {},
        )

    def finish(self, ctx: AuthContext, *, ok: bool, detail: str = "", correlation: dict[str, Any] | None = None) -> None:
        """Record the outcome of an authorized execution.

        Raises `AuditIntegrityError` if the row cannot be written: a successful
        mutation with no record is exactly the failure mode the Phase 4 audit
        found, so it must be loud rather than swallowed.
        """
        decision = DECISION_EXECUTED if ok else DECISION_FAILED
        try:
            self.grants.settle(ctx.grant_id, outcome="executed" if ok else "failed", request_id=ctx.request_id)
        except Exception:  # pragma: no cover - settle is best-effort bookkeeping
            pass
        self.audit.record_tx(
            request_id=ctx.request_id,
            principal=ctx.principal,
            action=ctx.action,
            resource=ctx.resource,
            decision=decision,
            grant_id=ctx.grant_id,
            result="ok" if ok else "failed",
            reason=detail,
            correlation=correlation or {},
        )

    def deny(
        self,
        *,
        request_id: str,
        principal: str,
        action: str,
        resource: str,
        reason: str,
        grant_id: str = "",
    ) -> None:
        self.audit.record_tx(
            request_id=request_id,
            principal=principal or "anonymous",
            action=action,
            resource=resource,
            decision=DECISION_REJECTED,
            grant_id=grant_id,
            result="denied",
            reason=reason,
        )

    # ------------------------------------------------------------ reporting
    def status(self) -> dict[str, Any]:
        chain = self.audit.verify()
        return {
            "authenticated": False,
            "principal_modes": ["operator-token", "internal-process"],
            "grants": self.grants.stats(),
            "audit": {
                "chain_ok": chain["ok"],
                "length": chain["length"],
                "head": chain.get("head", "")[:16],
                "counts": self.audit.counts(),
            },
            "policy": {
                "tools": len(policy.TOOL_CLASSES),
                "grant_required_classes": sorted(c.value for c in policy.GRANT_REQUIRED),
                "actions": sorted(policy.GRANTABLE_ACTIONS),
            },
        }
