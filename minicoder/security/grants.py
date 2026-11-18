"""Authorization grants: scoped, expiring, signed, single-use capabilities.

A grant is the *only* thing that authorizes a consequential operation.  It is

* **bound** to one action, one resource and one scope (a canonical instruction
  hash, a tool name, a label…) — a grant for ``export_image`` cannot authorize
  ``delete_elements``;
* **signed** with a server-held key so an identifier cannot be invented by a
  client, even if the client knows the grant table exists;
* **expiring** (default 120 s, destructive actions 60 s);
* **single use**: consumption is an atomic ``UPDATE … WHERE consumed_at IS NULL``
  inside ``BEGIN IMMEDIATE``, so two concurrent callers cannot both win;
* **attributable**: the principal fingerprint of the issuer is stored and must
  match the presenter.

No grant can be supplied by a request *body*: the store only reads identifiers
from an explicit header, and the legacy ``authorize: true`` boolean is not wired
to anything (the API rejects it as a no-op and audits the attempt).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from minicoder.config import CONFIG
from minicoder.memory.db import BrainDB, utcnow

DEFAULT_TTL = 120
DESTRUCTIVE_TTL = 60


class GrantError(Exception):
    """A grant was missing, malformed, forged, expired, replayed or mismatched."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class Grant:
    id: str
    principal: str
    action: str
    resource: str
    scope: str
    created_at: str
    expires_at: str
    nonce: str
    signature: str
    consumed_at: str | None = None
    consumed_by: str | None = None
    outcome: str = "issued"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "principal": self.principal,
            "action": self.action,
            "resource": self.resource,
            "scope": self.scope,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "consumed_at": self.consumed_at,
            "outcome": self.outcome,
        }


def _secret_path(name: str) -> Path:
    """Location of a server secret, outside the repository, mode 0600."""
    override = os.environ.get(f"NACE_{name.upper()}_FILE")
    if override:
        return Path(override)
    base = CONFIG.paths.home / ".security"
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base, 0o700)
    except OSError:
        pass
    return base / name


def _read_or_create_secret(name: str, nbytes: int = 32) -> str:
    path = _secret_path(name)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(nbytes)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, value.encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return value


def operator_token() -> str:
    """The operator capability token (0600 file outside the repo).

    This is a *capability*, not a user identity: whoever holds the file can act
    as the local operator.  The system has no user accounts and does not pretend
    otherwise (see ``docs/PHASE5_THREAT_MODEL.md``).
    """
    return _read_or_create_secret("operator.token", 32)


def principal_fingerprint(token: str) -> str:
    """Stable, non-reversible label for a token holder (never the token)."""
    digest = hashlib.sha256(("nace-principal:" + token).encode("utf-8")).hexdigest()
    return "operator:" + digest[:12]


class GrantStore:
    """Issuance, validation and atomic consumption of grants."""

    def __init__(self, db: BrainDB) -> None:
        self.db = db
        self._key = _read_or_create_secret("grant.key", 32)

    # ------------------------------------------------------------- signing
    def _signature(self, fields: tuple[str, ...]) -> str:
        msg = "|".join(fields).encode("utf-8")
        return hmac.new(self._key.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    @staticmethod
    def _fields(
        gid: str, principal: str, action: str, resource: str, scope: str,
        created_at: str, expires_at: str, nonce: str,
    ) -> tuple[str, ...]:
        return (gid, principal, action, resource, scope, created_at, expires_at, nonce)

    # ------------------------------------------------------------ issuance
    def issue(
        self,
        *,
        principal: str,
        action: str,
        resource: str,
        scope: str = "",
        ttl: int = DEFAULT_TTL,
        request_id: str = "",
        meta: dict[str, Any] | None = None,
    ) -> Grant:
        from minicoder.security.policy import GRANTABLE_ACTIONS

        if action not in GRANTABLE_ACTIONS:
            raise GrantError("unknown_action", action)
        if not principal:
            raise GrantError("missing_principal")
        gid = "g_" + secrets.token_hex(16)
        nonce = secrets.token_hex(16)
        created = utcnow()
        from datetime import UTC, datetime, timedelta

        expires = (datetime.now(UTC) + timedelta(seconds=max(1, int(ttl)))).isoformat(timespec="seconds")
        sig = self._signature(
            self._fields(gid, principal, action, resource, scope, created, expires, nonce)
        )
        with self.db.write() as conn:
            conn.execute(
                "INSERT INTO auth_grants(id, principal, action, resource, scope, created_at,"
                " expires_at, nonce, signature, outcome, meta, request_id)"
                " VALUES (?,?,?,?,?,?,?,?,?, 'issued', ?, ?)",
                (
                    gid,
                    principal,
                    action,
                    resource,
                    scope,
                    created,
                    expires,
                    nonce,
                    sig,
                    json.dumps(meta or {}),
                    request_id,
                ),
            )
        return Grant(gid, principal, action, resource, scope, created, expires, nonce, sig)

    # -------------------------------------------------------------- lookup
    def get(self, grant_id: str) -> Grant | None:
        row = self.db.query_one("SELECT * FROM auth_grants WHERE id=?", (grant_id,))
        if not row:
            return None
        return Grant(
            id=row["id"],
            principal=row["principal"],
            action=row["action"],
            resource=row["resource"],
            scope=row["scope"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            nonce=row["nonce"],
            signature=row["signature"],
            consumed_at=row["consumed_at"],
            consumed_by=row["consumed_by"],
            outcome=row["outcome"],
        )

    def _verify_signature(self, g: Grant) -> None:
        expected = self._signature(
            self._fields(g.id, g.principal, g.action, g.resource, g.scope,
                         g.created_at, g.expires_at, g.nonce)
        )
        if not hmac.compare_digest(expected, g.signature):
            raise GrantError("forged_grant", "signature does not match the stored record")

    @staticmethod
    def _expired(g: Grant, now: str) -> bool:
        return g.expires_at <= now

    def check_scope(self, g: Grant, *, principal: str, action: str, resource: str, scope: str) -> None:
        if g.principal != principal:
            raise GrantError("principal_mismatch", "grant was issued to another principal")
        if g.action != action:
            raise GrantError("action_mismatch", f"grant is for {g.action}, not {action}")
        if g.resource != resource:
            raise GrantError("resource_mismatch", f"grant is for {g.resource}, not {resource}")
        if (g.scope or "") != (scope or ""):
            raise GrantError("scope_mismatch", "grant does not cover this exact operation")

    # ---------------------------------------------------------- consumption
    def consume(
        self,
        grant_id: str,
        *,
        principal: str,
        action: str,
        resource: str,
        scope: str = "",
        request_id: str = "",
    ) -> Grant:
        """Atomically consume a grant or raise.  Exactly one caller can win."""
        if not grant_id:
            raise GrantError("missing_grant")
        with self.db.write() as conn:
            row = conn.execute("SELECT * FROM auth_grants WHERE id=?", (grant_id,)).fetchone()
            if not row:
                raise GrantError("unknown_grant", "no such grant")
            g = Grant(
                id=row["id"], principal=row["principal"], action=row["action"],
                resource=row["resource"], scope=row["scope"], created_at=row["created_at"],
                expires_at=row["expires_at"], nonce=row["nonce"], signature=row["signature"],
                consumed_at=row["consumed_at"], consumed_by=row["consumed_by"],
                outcome=row["outcome"],
            )
            self._verify_signature(g)
            self.check_scope(g, principal=principal, action=action, resource=resource, scope=scope)
            if g.consumed_at:
                raise GrantError("replayed", f"grant already consumed at {g.consumed_at}")
            now = utcnow()
            if self._expired(g, now):
                raise GrantError("expired", f"grant expired at {g.expires_at}")
            cur = conn.execute(
                "UPDATE auth_grants SET consumed_at=?, consumed_by=?, outcome='consumed'"
                " WHERE id=? AND consumed_at IS NULL",
                (now, request_id or "unknown", grant_id),
            )
            if cur.rowcount != 1:  # pragma: no cover - guarded by BEGIN IMMEDIATE
                raise GrantError("replayed", "lost the race for this grant")
        return Grant(
            id=g.id, principal=g.principal, action=g.action, resource=g.resource, scope=g.scope,
            created_at=g.created_at, expires_at=g.expires_at, nonce=g.nonce,
            signature=g.signature, consumed_at=now, consumed_by=request_id, outcome="consumed",
        )

    def settle(self, grant_id: str, *, outcome: str, request_id: str = "") -> None:
        """Record the outcome of a consumed grant: executed | failed."""
        if outcome not in {"executed", "failed"}:
            raise ValueError(outcome)
        with self.db.write() as conn:
            conn.execute(
                "UPDATE auth_grants SET outcome=? WHERE id=?", (outcome, grant_id)
            )

    def revoke(self, grant_id: str) -> bool:
        with self.db.write() as conn:
            cur = conn.execute(
                "UPDATE auth_grants SET outcome='revoked' WHERE id=? AND consumed_at IS NULL",
                (grant_id,),
            )
            return cur.rowcount == 1

    def purge_expired(self, older_than_seconds: int = 86400) -> int:
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(UTC) - timedelta(seconds=older_than_seconds)).isoformat(timespec="seconds")
        with self.db.write() as conn:
            cur = conn.execute("DELETE FROM auth_grants WHERE expires_at < ?", (cutoff,))
            return cur.rowcount

    def stats(self) -> dict[str, Any]:
        rows = self.db.query(
            "SELECT outcome, COUNT(*) c FROM auth_grants GROUP BY outcome ORDER BY outcome"
        )
        return {r["outcome"]: r["c"] for r in rows}
