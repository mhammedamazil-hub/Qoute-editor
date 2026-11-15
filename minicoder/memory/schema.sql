-- MiniCoder persistent memory schema (SQLite, WAL mode).
-- Every table that stores knowledge carries provenance + verification columns,
-- satisfying prime directives #2 (never train on unverified data) and #4
-- (always maintain provenance).

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ---------------------------------------------------------------- episodes
CREATE TABLE IF NOT EXISTS episodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    modality    TEXT    NOT NULL CHECK (modality IN ('text','code','vision','mixed')),
    situation   TEXT    NOT NULL,
    objective   TEXT    NOT NULL,
    actions     TEXT    NOT NULL DEFAULT '[]',   -- JSON array
    result      TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL CHECK (status IN ('VERIFIED','UNVERIFIED','FAILED','QUARANTINED')),
    source      TEXT    NOT NULL,
    mistakes    TEXT    NOT NULL DEFAULT '',
    lessons     TEXT    NOT NULL DEFAULT '',
    confidence  REAL    NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    surprise    REAL    NOT NULL DEFAULT 0.0,    -- prioritised replay weight
    session_id  TEXT    NOT NULL DEFAULT '',
    consolidated INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0,
    meta        TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(ts DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_unconsolidated ON episodes(consolidated, archived);

-- ------------------------------------------------------- semantic knowledge
CREATE TABLE IF NOT EXISTS semantic_nodes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT    NOT NULL,     -- concept | fact | idiom | heuristic | user_preference | pattern
    label        TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    status       TEXT    NOT NULL CHECK (status IN ('VERIFIED','UNVERIFIED','FAILED','QUARANTINED')),
    source       TEXT    NOT NULL,
    confidence   REAL    NOT NULL DEFAULT 0.5,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_access  TEXT    NOT NULL,
    archived     INTEGER NOT NULL DEFAULT 0,
    meta         TEXT    NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_semantic_label ON semantic_nodes(kind, label);
CREATE INDEX IF NOT EXISTS idx_semantic_recent ON semantic_nodes(last_access DESC);

CREATE TABLE IF NOT EXISTS semantic_edges (
    src        INTEGER NOT NULL REFERENCES semantic_nodes(id) ON DELETE CASCADE,
    dst        INTEGER NOT NULL REFERENCES semantic_nodes(id) ON DELETE CASCADE,
    relation   TEXT    NOT NULL,      -- causes | solves | depends_on | visually_resembles | contradicts | refines
    weight     REAL    NOT NULL DEFAULT 1.0,
    created_at TEXT    NOT NULL,
    PRIMARY KEY (src, dst, relation)
);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON semantic_edges(dst);

-- ------------------------------------------------------------ procedural
CREATE TABLE IF NOT EXISTS skills (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    slug           TEXT    NOT NULL UNIQUE,
    name           TEXT    NOT NULL,
    domain         TEXT    NOT NULL DEFAULT 'general',
    description    TEXT    NOT NULL,
    params_schema  TEXT    NOT NULL DEFAULT '{}',
    reasoning      TEXT    NOT NULL DEFAULT '[]',   -- JSON chain of thought
    tool_calls     TEXT    NOT NULL DEFAULT '[]',   -- JSON trajectories
    solution       TEXT    NOT NULL DEFAULT '',     -- executable body when applicable
    verification   TEXT    NOT NULL DEFAULT '{}',   -- JSON {tests, passed, runner, hash}
    status         TEXT    NOT NULL CHECK (status IN ('VERIFIED','UNVERIFIED','FAILED','QUARANTINED')),
    source         TEXT    NOT NULL,
    confidence     REAL    NOT NULL DEFAULT 0.5,
    episode_ids    TEXT    NOT NULL DEFAULT '[]',
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL,
    verified_at    TEXT,
    used_count     INTEGER NOT NULL DEFAULT 0,
    last_used      TEXT,
    exported       INTEGER NOT NULL DEFAULT 0,
    meta           TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status, exported);

-- ---------------------------------------------------------------- vision
CREATE TABLE IF NOT EXISTS visual_memories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,
    image_path    TEXT    NOT NULL,
    thumb_path    TEXT    NOT NULL DEFAULT '',
    sha256        TEXT    NOT NULL,
    width         INTEGER NOT NULL DEFAULT 0,
    height        INTEGER NOT NULL DEFAULT 0,
    ocr_text      TEXT    NOT NULL DEFAULT '',
    description   TEXT    NOT NULL DEFAULT '',
    boxes         TEXT    NOT NULL DEFAULT '[]',
    labels        TEXT    NOT NULL DEFAULT '[]',
    status        TEXT    NOT NULL CHECK (status IN ('VERIFIED','UNVERIFIED','FAILED','QUARANTINED')),
    source        TEXT    NOT NULL,
    episode_id    INTEGER REFERENCES episodes(id) ON DELETE SET NULL,
    meta          TEXT    NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_visual_sha ON visual_memories(sha256);

-- --------------------------------------------------------------- vectors
CREATE TABLE IF NOT EXISTS embeddings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner      TEXT    NOT NULL,        -- episodes | semantic_nodes | skills | visual_memories
    owner_id   INTEGER NOT NULL,
    kind       TEXT    NOT NULL,        -- text | image | text_image
    model      TEXT    NOT NULL,
    dim        INTEGER NOT NULL,
    created_at TEXT    NOT NULL,
    UNIQUE (owner, owner_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_embeddings_owner ON embeddings(owner, owner_id);

-- vec0 virtual table created by db.py once sqlite-vec is loaded (dim from config).

-- ------------------------------------------------------------- audit log
CREATE TABLE IF NOT EXISTS provenance_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    entity    TEXT NOT NULL,
    entity_id INTEGER,
    action    TEXT NOT NULL,
    actor     TEXT NOT NULL DEFAULT 'brain',
    detail    TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_prov_entity ON provenance_events(entity, entity_id);

-- ------------------------------------------------------------- conflicts
CREATE TABLE IF NOT EXISTS memory_conflicts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT    NOT NULL,
    node_a     INTEGER NOT NULL,
    node_b     INTEGER NOT NULL,
    reason     TEXT    NOT NULL,
    resolved   INTEGER NOT NULL DEFAULT 0,
    resolution TEXT    NOT NULL DEFAULT ''
);

-- --------------------------------------------------------- sleep cycles
CREATE TABLE IF NOT EXISTS sleep_cycles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT    NOT NULL,
    ended_at    TEXT,
    trigger     TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'running',
    report      TEXT    NOT NULL DEFAULT '{}'
);

-- -------------------------------------------------------- dataset shards
CREATE TABLE IF NOT EXISTS dataset_shards (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT    NOT NULL UNIQUE,
    sha256     TEXT    NOT NULL,
    examples   INTEGER NOT NULL,
    created_at TEXT    NOT NULL,
    pushed     INTEGER NOT NULL DEFAULT 0,
    commit_sha TEXT    NOT NULL DEFAULT '',
    meta       TEXT    NOT NULL DEFAULT '{}'
);

-- ------------------------------------------------------- training runs
CREATE TABLE IF NOT EXISTS training_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT    NOT NULL,
    shard_path   TEXT    NOT NULL DEFAULT '',
    base_ckpt    TEXT    NOT NULL,
    adapter_path TEXT    NOT NULL DEFAULT '',
    gate_passed  INTEGER,
    metrics      TEXT    NOT NULL DEFAULT '{}',
    notes        TEXT    NOT NULL DEFAULT ''
);

-- ------------------------------------------------------------ telemetry
CREATE TABLE IF NOT EXISTS telemetry (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    TEXT NOT NULL,
    state TEXT NOT NULL,
    event TEXT NOT NULL,
    data  TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(ts DESC);

INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', '1');
INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('created_at', datetime('now'));
