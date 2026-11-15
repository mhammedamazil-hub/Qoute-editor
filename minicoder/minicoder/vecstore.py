"""Vector store inside the same SQLite file as everything else.

Uses the official sqlite-vec extension when present; otherwise falls back to
a pure-NumPy cosine scan over the `vectors` table. Either way: single file,
zero external services, works offline.
"""
from __future__ import annotations
import sqlite3
import numpy as np
from .config import get_settings
from .embeddings import from_blob, to_blob, embed_text, cosine
from .util import now_iso

try:
    import sqlite_vec  # type: ignore
    _HAVE_SQLIVEC = True
except Exception:  # pragma: no cover - depends on platform wheel availability
    sqlite_vec = None
    _HAVE_SQLIVEC = False


def _try_load_extension(con: sqlite3.Connection) -> bool:
    if not _HAVE_SQLIVEC:
        return False
    try:
        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
        return True
    except Exception:
        return False


def upsert_vector(con: sqlite3.Connection, entity_id: str, kind: str, vec: np.ndarray) -> None:
    con.execute(
        "INSERT INTO vectors(id, kind, dim, blob, created_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, dim=excluded.dim, blob=excluded.blob",
        (entity_id, kind, int(vec.shape[0]), sqlite3.Binary(to_blob(vec)), now_iso()),
    )


def search_vectors(con: sqlite3.Connection, query: np.ndarray, kind: str | None = None,
                   top_k: int = 6) -> list[tuple[str, float]]:
    """Returns [(entity_id, similarity)] sorted desc. sqlite-vec fast path,
    numpy fallback — both read from the same table, results identical modulo
    floating point."""
    if top_k <= 0:
        return []
    if _try_load_extension(con):
        try:
            return _search_sqlite_vec(con, query, kind, top_k)
        except sqlite3.Error:
            pass  # fall through to numpy path
    return _search_numpy(con, query, kind, top_k)


def _search_numpy(con: sqlite3.Connection, query: np.ndarray, kind: str | None,
                  top_k: int) -> list[tuple[str, float]]:
    sql = "SELECT id, blob FROM vectors"
    params: list = []
    if kind:
        sql += " WHERE kind=?"
        params.append(kind)
    rows = con.execute(sql, params).fetchall()
    scored = [(r["id"], cosine(query, from_blob(r["blob"]))) for r in rows]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored[:top_k]


def _search_sqlite_vec(con: sqlite3.Connection, query: np.ndarray, kind: str | None,
                       top_k: int) -> list[tuple[str, float]]:
    # sqlite-vec 0.1.x: vec0 virtual tables keyed by rowid + auxiliary columns.
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_items'").fetchone()
    if row is None:
        dim = int(query.shape[0])
        con.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0("
            f"entity_id TEXT PRIMARY KEY, embedding float[{dim}])")
        for r in con.execute("SELECT id, blob, dim FROM vectors").fetchall():
            if int(r["dim"]) == dim:
                con.execute("INSERT OR REPLACE INTO vec_items(entity_id, embedding) VALUES (?, ?)",
                            (r["id"], to_blob(from_blob(r["blob"]))))
    q = to_blob(query)
    if kind:
        rows = con.execute(
            "SELECT v.entity_id AS id, vec_distance_cosine(v.embedding, ?) AS dist "
            "FROM vec_items v JOIN vectors m ON m.id = v.entity_id "
            "WHERE m.kind = ? ORDER BY dist ASC LIMIT ?", (q, kind, top_k)).fetchall()
    else:
        rows = con.execute(
            "SELECT entity_id AS id, vec_distance_cosine(embedding, ?) AS dist "
            "FROM vec_items ORDER BY dist ASC LIMIT ?", (q, top_k)).fetchall()
    return [(r["id"], 1.0 - float(r["dist"])) for r in rows]


def embed_and_store(con: sqlite3.Connection, entity_id: str, kind: str, text: str) -> None:
    upsert_vector(con, entity_id, kind, embed_text(text))
