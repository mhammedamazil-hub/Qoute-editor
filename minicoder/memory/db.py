"""SQLite brain store: connection management, migrations, atomic backups.

The whole persistent memory lives in a single ``brain.db`` file (WAL mode) with
``sqlite-vec`` loaded for vector search.  Durability requirements come from
prime directive #3: nothing may destroy the working model or memory, so every
mutating batch is wrapped in a transaction and backups are atomic snapshots
taken with ``VACUUM INTO``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import sqlite_vec

from minicoder.config import CONFIG, MemoryConfig, Paths

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def utcnow() -> str:
    """ISO-8601 UTC timestamp with second precision (sortable as text)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class BrainDB:
    """Thread-safe wrapper around the SQLite brain.

    One connection per thread is required for ``check_same_thread`` safety in
    the async API; the wrapper caches them and serialises writes with a lock.
    """

    def __init__(self, paths: Paths | None = None, memory: MemoryConfig | None = None) -> None:
        self.paths = (paths or CONFIG.paths).ensure()
        self.mem = memory or CONFIG.memory
        self.db_path = self.paths.brain_db
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._init_db()

    # ------------------------------------------------------------ plumbing
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """Serialised write transaction; rolls back on any exception."""
        with self._write_lock:
            conn = self.conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self.write() as conn:
            return conn.execute(sql, params)

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    # ---------------------------------------------------------------- init
    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self.conn
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        # sqlite-vec virtual table for dense retrieval.
        dim = self.mem.embedding_dim
        conn.execute(
            f"""CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(
                    embedding_id INTEGER PRIMARY KEY,
                    embedding FLOAT[{dim}]
                )"""
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('embedding_dim', ?)",
            (str(dim),),
        )

    # ------------------------------------------------------------ backups
    def backup(self, tag: str = "manual") -> Path:
        """Atomic, consistent snapshot of the whole brain (VACUUM INTO)."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = self.paths.checkpoints / f"brain_{tag}_{stamp}.db"
        tmp = dest.with_suffix(".tmp")
        if tmp.exists():
            tmp.unlink()
        # VACUUM INTO writes a complete, transactionally consistent copy.
        self.conn.execute("VACUUM INTO ?", (str(tmp),))
        os.replace(tmp, dest)
        self.log_provenance("brain", None, "backup", detail={"path": str(dest)})
        return dest

    def verify_integrity(self) -> dict[str, Any]:
        row = self.query_one("PRAGMA integrity_check")
        ok = bool(row and row[0] == "ok")
        counts = {}
        for table in (
            "episodes",
            "semantic_nodes",
            "semantic_edges",
            "skills",
            "visual_memories",
            "embeddings",
            "provenance_events",
            "dataset_shards",
        ):
            counts[table] = self.query_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]
        return {"ok": ok, "detail": row[0] if row else "no result", "counts": counts}

    def restore(self, snapshot: Path) -> None:
        """Rollback to a snapshot, keeping the current brain as a safety copy."""
        snapshot = Path(snapshot)
        if not snapshot.exists():
            raise FileNotFoundError(snapshot)
        safety = self.backup(tag="pre_restore")
        self._local.conn.close()
        self._local.conn = None
        for suffix in ("-wal", "-shm"):
            side = Path(str(self.db_path) + suffix)
            if side.exists():
                side.unlink()
        shutil.copy2(snapshot, self.db_path)
        self._init_db()
        self.log_provenance(
            "brain", None, "restore", detail={"from": str(snapshot), "safety": str(safety)}
        )

    # ---------------------------------------------------------- provenance
    def log_provenance(
        self,
        entity: str,
        entity_id: int | None,
        action: str,
        actor: str = "brain",
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.execute(
            "INSERT INTO provenance_events(ts, entity, entity_id, action, actor, detail)"
            " VALUES (?,?,?,?,?,?)",
            (utcnow(), entity, entity_id, action, actor, json.dumps(detail or {})),
        )

    def telemetry(self, state: str, event: str, data: dict[str, Any] | None = None) -> None:
        self.execute(
            "INSERT INTO telemetry(ts, state, event, data) VALUES (?,?,?,?)",
            (utcnow(), state, event, json.dumps(data or {})),
        )

    # ------------------------------------------------------------ vectors
    def upsert_embedding(
        self, owner: str, owner_id: int, kind: str, model: str, vector: list[float]
    ) -> int:
        payload = json.dumps([round(float(v), 6) for v in vector])
        dim = len(vector)
        with self.write() as conn:
            row = conn.execute(
                "SELECT id FROM embeddings WHERE owner=? AND owner_id=? AND kind=?",
                (owner, owner_id, kind),
            ).fetchone()
            if row:
                eid = row["id"]
                conn.execute(
                    "UPDATE embeddings SET model=?, dim=?, created_at=? WHERE id=?",
                    (model, dim, utcnow(), eid),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO vec_items(embedding_id, embedding) VALUES (?, ?)",
                    (eid, payload),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO embeddings(owner, owner_id, kind, model, dim, created_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (owner, owner_id, kind, model, dim, utcnow()),
                )
                eid = int(cur.lastrowid)
                conn.execute(
                    "INSERT INTO vec_items(embedding_id, embedding) VALUES (?, ?)",
                    (eid, payload),
                )
        return eid

    def delete_embedding(self, owner: str, owner_id: int) -> None:
        with self.write() as conn:
            rows = conn.execute(
                "SELECT id FROM embeddings WHERE owner=? AND owner_id=?", (owner, owner_id)
            ).fetchall()
            for row in rows:
                conn.execute("DELETE FROM vec_items WHERE embedding_id=?", (row["id"],))
            conn.execute("DELETE FROM embeddings WHERE owner=? AND owner_id=?", (owner, owner_id))

    def vector_search(
        self,
        vector: list[float],
        owner: str | None = None,
        kinds: tuple[str, ...] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        payload = json.dumps([round(float(v), 6) for v in vector])
        rows = self.conn.execute(
            "SELECT embedding_id, distance FROM vec_items WHERE embedding MATCH ? AND k = ?",
            (payload, max(limit * 3, limit)),
        ).fetchall()
        if not rows:
            return []
        ids = [r["embedding_id"] for r in rows]
        dist = {r["embedding_id"]: r["distance"] for r in rows}
        placeholders = ",".join("?" * len(ids))
        sql = f"SELECT * FROM embeddings WHERE id IN ({placeholders})"
        params: list[Any] = list(ids)
        if owner:
            sql += " AND owner = ?"
            params.append(owner)
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            params.extend(kinds)
        out = []
        for row in self.conn.execute(sql, params).fetchall():
            out.append(
                {
                    "owner": row["owner"],
                    "owner_id": row["owner_id"],
                    "kind": row["kind"],
                    "distance": float(dist[row["id"]]),
                    "similarity": 1.0 - float(dist[row["id"]]),
                }
            )
        out.sort(key=lambda r: r["distance"])
        return out[:limit]

    # ---------------------------------------------------------- stats
    def stats(self) -> dict[str, Any]:
        def count(sql: str, params: tuple = ()) -> int:
            row = self.query_one(sql, params)
            return int(row[0]) if row else 0

        return {
            "episodes": count("SELECT COUNT(*) FROM episodes WHERE archived=0"),
            "episodes_total": count("SELECT COUNT(*) FROM episodes"),
            "semantic_nodes": count("SELECT COUNT(*) FROM semantic_nodes WHERE archived=0"),
            "semantic_edges": count("SELECT COUNT(*) FROM semantic_edges"),
            "skills_verified": count("SELECT COUNT(*) FROM skills WHERE status='VERIFIED'"),
            "skills_total": count("SELECT COUNT(*) FROM skills"),
            "skills_pending_export": count(
                "SELECT COUNT(*) FROM skills WHERE status='VERIFIED' AND exported=0"
            ),
            "visual_memories": count("SELECT COUNT(*) FROM visual_memories"),
            "embeddings": count("SELECT COUNT(*) FROM embeddings"),
            "sleep_cycles": count("SELECT COUNT(*) FROM sleep_cycles"),
            "shards": count("SELECT COUNT(*) FROM dataset_shards"),
            "conflicts_open": count("SELECT COUNT(*) FROM memory_conflicts WHERE resolved=0"),
            "db_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
        }

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
