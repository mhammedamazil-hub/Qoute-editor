"""Hash-chained security audit.

Every consequential request produces at least one row here: the decision that
was taken, and (for executions) the outcome.  The chain makes silent deletion or
edit of a past row detectable, which is the property the Phase 4 audit found
missing (`audit_log` was a plain insert table that any code path could rewrite).

Two rules govern writes:

* **Never swallow.**  `record` raises if the row cannot be written.  A caller
  that cannot record an authorization must not execute the operation — that is
  the fail-closed order used by :mod:`minicoder.security.service`.
* **Never store secrets.**  Rows carry a principal *fingerprint*, never a token;
  `record` rejects any field that looks like a bearer credential.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from minicoder.memory.db import BrainDB, utcnow

GENESIS = "0" * 64

DECISION_REQUESTED = "requested"
DECISION_AUTHORIZED = "authorized"
DECISION_EXECUTED = "executed"
DECISION_FAILED = "failed"
DECISION_REJECTED = "rejected"
DECISION_REPLAYED = "replayed"

DECISIONS = frozenset(
    {
        DECISION_REQUESTED,
        DECISION_AUTHORIZED,
        DECISION_EXECUTED,
        DECISION_FAILED,
        DECISION_REJECTED,
        DECISION_REPLAYED,
    }
)

_SECRET_PATTERNS = (
    re.compile(r"\bnace_[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{16,}", re.I),
)


class AuditIntegrityError(RuntimeError):
    """Raised when an audit row could not be written or the chain is broken."""


def _assert_no_secrets(payload: dict[str, Any]) -> None:
    blob = json.dumps(payload, default=str)
    for pat in _SECRET_PATTERNS:
        if pat.search(blob):
            raise AuditIntegrityError("refusing to write a credential into the audit log")


def _canonical(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)


def _digest(prev_hash: str, row: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + "|" + _canonical(row)).encode("utf-8")).hexdigest()


class SecurityAudit:
    """Append-only, hash-chained audit trail for authorization decisions."""

    def __init__(self, db: BrainDB) -> None:
        self.db = db

    # ------------------------------------------------------------- writing
    def record(
        self,
        conn,
        *,
        request_id: str,
        principal: str,
        action: str,
        resource: str,
        decision: str,
        grant_id: str = "",
        result: str = "",
        reason: str = "",
        correlation: dict[str, Any] | None = None,
    ) -> str:
        """Append one row inside the caller's transaction.  Returns its hash.

        Raising here is intentional: the caller is expected to abort the
        operation when the audit cannot be written.
        """
        if decision not in DECISIONS:
            raise AuditIntegrityError(f"unknown decision {decision!r}")
        corr = correlation or {}
        _assert_no_secrets({"result": result, "reason": reason, "correlation": corr})
        ts = utcnow()
        prev = conn.execute("SELECT hash FROM security_audit ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = prev["hash"] if prev else GENESIS
        row = {
            "ts": ts,
            "request_id": str(request_id or ""),
            "principal": str(principal or ""),
            "action": str(action or ""),
            "resource": str(resource or ""),
            "decision": decision,
            "grant_id": str(grant_id or ""),
            "result": str(result or "")[:2000],
            "reason": str(reason or "")[:2000],
            "correlation": corr,
            "prev_hash": prev_hash,
        }
        digest = _digest(prev_hash, row)
        conn.execute(
            "INSERT INTO security_audit(ts, request_id, principal, action, resource, decision,"
            " grant_id, result, reason, correlation, prev_hash, hash)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ts,
                row["request_id"],
                row["principal"],
                row["action"],
                row["resource"],
                decision,
                row["grant_id"],
                row["result"],
                row["reason"],
                json.dumps(corr, sort_keys=True, default=str),
                prev_hash,
                digest,
            ),
        )
        # Anchor the head outside the table: deleting the newest row would
        # otherwise leave a shorter but internally consistent chain.
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('security_audit_head', ?)",
            (digest,),
        )
        return digest

    def record_tx(self, **kwargs: Any) -> str:
        """Append a row in its own transaction (used for rejections)."""
        with self.db.write() as conn:
            return self.record(conn, **kwargs)

    # ------------------------------------------------------------- reading
    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT id, ts, request_id, principal, action, resource, decision, grant_id,"
            " result, reason, prev_hash, hash FROM security_audit ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def by_request(self, request_id: str) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM security_audit WHERE request_id=? ORDER BY id", (request_id,)
        )
        return [dict(r) for r in rows]

    def counts(self) -> dict[str, int]:
        rows = self.db.query(
            "SELECT decision, COUNT(*) c FROM security_audit GROUP BY decision ORDER BY decision"
        )
        return {r["decision"]: r["c"] for r in rows}

    def verify(self, limit: int | None = None) -> dict[str, Any]:
        """Recompute the chain and report the first row that does not match."""
        sql = "SELECT * FROM security_audit ORDER BY id"
        rows = self.db.query(sql) if limit is None else self.db.query(sql + " LIMIT ?", (limit,))
        prev = GENESIS
        for r in rows:
            row = {
                "ts": r["ts"],
                "request_id": r["request_id"],
                "principal": r["principal"],
                "action": r["action"],
                "resource": r["resource"],
                "decision": r["decision"],
                "grant_id": r["grant_id"],
                "result": r["result"],
                "reason": r["reason"],
                "correlation": json.loads(r["correlation"] or "{}"),
                "prev_hash": r["prev_hash"],
            }
            expected = _digest(prev, row)
            if r["prev_hash"] != prev or r["hash"] != expected:
                return {
                    "ok": False,
                    "length": len(rows),
                    "broken_at": int(r["id"]),
                    "reason": "hash chain mismatch",
                }
            prev = r["hash"]
        anchored = self.db.query_one(
            "SELECT value FROM schema_meta WHERE key='security_audit_head'"
        )
        anchor = anchored["value"] if anchored else GENESIS
        if prev != anchor:
            return {
                "ok": False,
                "length": len(rows),
                "broken_at": None,
                "reason": "chain head does not match the anchored head (rows removed)",
            }
        return {"ok": True, "length": len(rows), "head": prev}
