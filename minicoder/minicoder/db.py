"""SQLite (WAL mode) substrate for the whole brain.

One file — brain.db — holds episodic memory, provenance, the semantic
graph adjacency tables, the procedural registry, vector blobs (fallback
when sqlite-vec is unavailable), the sleep ledger and key/value meta.
Atomic backups + snapshot export live in snapshot.py.
"""
from __future__ import annotations
import json
import shutil
import sqlite3
import threading
from pathlib import Path
from .config import get_settings
from .util import now_iso, utcnow_compact

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes (
  id TEXT PRIMARY KEY,
  situation TEXT NOT NULL,
  modality TEXT NOT NULL DEFAULT 'text',
  objective TEXT NOT NULL DEFAULT '',
  actions_json TEXT NOT NULL DEFAULT '[]',
  result TEXT NOT NULL DEFAULT '',
  verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
  mistakes_json TEXT NOT NULL DEFAULT '[]',
  lessons_json TEXT NOT NULL DEFAULT '[]',
  source TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.5,
  access_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  archived INTEGER NOT NULL DEFAULT 0,
  tags_json TEXT NOT NULL DEFAULT '[]',
  meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at);
CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(verification_status);
CREATE INDEX IF NOT EXISTS idx_episodes_archived ON episodes(archived);
CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(situation, objective, result, content='episodes', content_rowid='rowid');

CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
  INSERT INTO episodes_fts(rowid, situation, objective, result) VALUES (new.rowid, new.situation, new.objective, new.result);
END;
CREATE TRIGGER IF NOT EXISTS episodes_au AFTER UPDATE ON episodes BEGIN
  INSERT INTO episodes_fts(episodes_fts, rowid, situation, objective, result) VALUES('delete', old.rowid, old.situation, old.objective, old.result);
  INSERT INTO episodes_fts(rowid, situation, objective, result) VALUES (new.rowid, new.situation, new.objective, new.result);
END;
CREATE TRIGGER IF NOT EXISTS episodes_ad AFTER DELETE ON episodes BEGIN
  INSERT INTO episodes_fts(episodes_fts, rowid, situation, objective, result) VALUES('delete', old.rowid, old.situation, old.objective, old.result);
END;

CREATE TABLE IF NOT EXISTS concepts (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'concept',   -- concept|fact|preference|heuristic|skill
  confidence REAL NOT NULL DEFAULT 0.5,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  archived INTEGER NOT NULL DEFAULT 0,
  meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_concepts_label ON concepts(lower(label));

CREATE TABLE IF NOT EXISTS relations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  src TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  dst TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
  relation TEXT NOT NULL,                 -- causes|solves|depends_on|visually_resembles|related_to|contradicts|part_of
  confidence REAL NOT NULL DEFAULT 0.5,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(src, dst, relation)
);
CREATE INDEX IF NOT EXISTS idx_relations_src ON relations(src);
CREATE INDEX IF NOT EXISTS idx_relations_dst ON relations(dst);
CREATE INDEX IF NOT EXISTS idx_relations_rel ON relations(relation);

CREATE TABLE IF NOT EXISTS vectors (
  id TEXT PRIMARY KEY,           -- episode id or concept id or skill id
  kind TEXT NOT NULL,            -- episode|concept|skill|image
  dim INTEGER NOT NULL,
  blob BLOB NOT NULL,            -- float32 little-endian
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  domain TEXT NOT NULL DEFAULT 'general',
  verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
  confidence REAL NOT NULL DEFAULT 0.5,
  path TEXT NOT NULL,            -- YAML file under procedural/
  times_used INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sleep_runs (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  trigger TEXT NOT NULL,
  report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_kind TEXT NOT NULL,     -- episode|concept|skill|image|shard
  entity_id TEXT NOT NULL,
  source TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prov_entity ON provenance(entity_kind, entity_id);
"""

_lock = threading.RLock()


_initialized: set[str] = set()


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (and if necessary, initialise) the brain database.

    Auto-bootstraps the schema on first use per process — callers never need
    to remember init_db() before touching the store."""
    settings = get_settings()
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    key = str(path)
    fresh = key not in _initialized
    con = sqlite3.connect(str(path), timeout=30.0, isolation_level=None)  # autocommit; explicit txn where needed
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    if fresh:
        with _lock:
            con.executescript(_SCHEMA)
            con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', '1')")
            con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('created_at', ?)", (now_iso(),))
            settings.ensure_dirs()
            _initialized.add(key)
    return con


def init_db(db_path: Path | None = None) -> Path:
    path = db_path or get_settings().db_path
    with connect(path):
        pass  # schema applied on connect
    return path


def backup_db(reason: str = "manual") -> Path | None:
    """Atomic, non-destructive backup before any risky operation (sleep, import, model swap)."""
    settings = get_settings()
    src = settings.db_path
    if not src.exists():
        return None
    stamp = utcnow_compact()
    dst = settings.backups / f"brain_{stamp}_{reason}.db"
    dst.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        src_con = sqlite3.connect(str(src))
        try:
            dst_con = sqlite3.connect(str(dst))
            try:
                src_con.backup(dst_con)
            finally:
                dst_con.close()
        finally:
            src_con.close()
    # keep last 10 backups
    backups = sorted(settings.backups.glob("brain_*.db"))
    for old in backups[:-10]:
        try:
            old.unlink()
        except OSError:
            pass
    return dst


def get_meta(con: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def log_provenance(con: sqlite3.Connection, entity_kind: str, entity_id: str, source: str, detail: str = "") -> None:
    con.execute(
        "INSERT INTO provenance(entity_kind, entity_id, source, detail, created_at) VALUES (?,?,?,?,?)",
        (entity_kind, entity_id, str(source), detail, now_iso()),
    )


def counts(db_path: Path | None = None) -> dict[str, int]:
    with connect(db_path) as con:
        out = {}
        for table in ("episodes", "concepts", "relations", "skills", "sleep_runs", "provenance", "vectors"):
            out[table] = con.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
        out["episodes_active"] = con.execute("SELECT COUNT(*) c FROM episodes WHERE archived=0").fetchone()["c"]
        out["skills_verified"] = con.execute("SELECT COUNT(*) c FROM skills WHERE verification_status='VERIFIED'").fetchone()["c"]
        return out


def export_json_snapshot(db_path: Path | None = None) -> dict:
    """Full logical export (used by snapshot.py)."""
    with connect(db_path) as con:
        snap = {}
        for table in ("meta", "episodes", "concepts", "relations", "skills", "sleep_runs", "provenance"):
            rows = [dict(r) for r in con.execute(f"SELECT * FROM {table}")]
            snap[table] = rows
        snap["exported_at"] = now_iso()
        return snap


def import_json_snapshot(snap: dict, db_path: Path | None = None) -> dict[str, int]:
    """Merge import: never deletes, upserts rows by primary key. Caller must backup first."""
    path = db_path or get_settings().db_path
    init_db(path)
    imported: dict[str, int] = {}
    with _lock, connect(path) as con:
        con.execute("BEGIN")
        try:
            for table in ("episodes", "concepts", "relations", "skills", "sleep_runs", "provenance"):
                rows = snap.get(table, [])
                if not rows:
                    imported[table] = 0
                    continue
                cols = list(rows[0].keys())
                placeholders = ",".join("?" for _ in cols)
                collist = ",".join(cols)
                n = 0
                for row in rows:
                    con.execute(f"INSERT OR IGNORE INTO {table} ({collist}) VALUES ({placeholders})", [row.get(c) for c in cols])
                    n += 1
                imported[table] = n
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    return imported
