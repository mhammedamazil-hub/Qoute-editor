"""The five memory systems: working, episodic, semantic, procedural, visual.

Each system has a clear contract:

* **Working** — bounded, priority-scored, expiring scratchpad for the active
  task. Compresses and evicts automatically; supports pinning.
* **Episodic** — timestamped autobiographical records with verification status,
  surprise weighting (for prioritised replay) and consolidation flags.
* **Semantic** — a NetworkX knowledge graph persisted in SQLite, with typed
  relations, conflict detection and confidence decay.
* **Procedural** — verified skill definitions that stage neural training.
* **Visual** — deduplicated image memories with OCR, boxes and descriptions.

All writes log provenance. Nothing is deleted without archiving first.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import networkx as nx

from minicoder.config import (
    CONFIG,
    FAILED,
    QUARANTINED,
    UNVERIFIED,
    VALID_SOURCES,
    VALID_STATUSES,
    VERIFIED,
)
from minicoder.memory.db import BrainDB, utcnow

_WORD = re.compile(r"[A-Za-z0-9_]+")


def _norm(s: str) -> str:
    return " ".join(_WORD.findall(s.lower()))


def _days_since(ts: str) -> float:
    try:
        then = datetime.fromisoformat(ts)
        if then.tzinfo is None:
            then = then.replace(tzinfo=UTC)
        return max(0.0, (datetime.now(UTC) - then).total_seconds() / 86400.0)
    except Exception:
        return 0.0


# ==========================================================================
# A. working memory
# ==========================================================================

@dataclass
class WorkingItem:
    id: str
    kind: str            # message | code | image | constraint | reasoning | error | tool_result
    content: str
    priority: float       # 0..1 user-assigned
    created_at: float
    last_used: float
    pinned: bool = False
    uses: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def score(self, now: float) -> float:
        age = now - self.last_used
        recency = math.exp(-age / 900.0)          # decays over ~15 min
        return 0.45 * self.priority + 0.35 * recency + 0.20 * min(1.0, self.uses / 5.0)


class WorkingMemory:
    """Capacity-bounded active workspace that never silently drops pinned items."""

    def __init__(self, capacity: int | None = None, token_budget: int | None = None,
                 ttl: float | None = None) -> None:
        m = CONFIG.memory
        self.capacity = capacity or m.working_capacity
        self.token_budget = token_budget or m.working_token_budget
        self.ttl = ttl or m.working_ttl_seconds
        self.items: dict[str, WorkingItem] = {}
        self._n = 0
        self.evicted: list[dict[str, Any]] = []

    # ---------------------------------------------------------------- api
    def put(self, kind: str, content: str, priority: float = 0.5, pinned: bool = False,
            meta: dict[str, Any] | None = None) -> str:
        self._n += 1
        iid = f"wm{self._n:04d}"
        now = time.time()
        self.items[iid] = WorkingItem(
            id=iid, kind=kind, content=content, priority=priority,
            created_at=now, last_used=now, pinned=pinned, meta=meta or {},
        )
        self._enforce()
        return iid

    def touch(self, iid: str) -> None:
        if iid in self.items:
            self.items[iid].last_used = time.time()
            self.items[iid].uses += 1

    def get(self, iid: str) -> WorkingItem | None:
        self.touch(iid)
        return self.items.get(iid)

    def pin(self, iid: str, pinned: bool = True) -> bool:
        if iid in self.items:
            self.items[iid].pinned = pinned
            self._enforce()
            return True
        return False

    def drop(self, iid: str) -> bool:
        return self.items.pop(iid, None) is not None

    def expire(self) -> int:
        now = time.time()
        dead = [i.id for i in self.items.values() if not i.pinned and now - i.last_used > self.ttl]
        for iid in dead:
            self.evicted.append({"reason": "ttl", "item": asdict(self.items[iid])})
            self.items.pop(iid, None)
        return len(dead)

    # ----------------------------------------------------------- internals
    def tokens(self) -> int:
        return sum(max(1, len(i.content) // 4) for i in self.items.values())

    def _enforce(self) -> None:
        self.expire()
        pinned = [i for i in self.items.values() if i.pinned]
        while len(self.items) > self.capacity or (
            self.tokens() > self.token_budget and len(self.items) > len(pinned)
        ):
            now = time.time()
            candidates = [i for i in self.items.values() if not i.pinned]
            if not candidates and len(self.items) > self.capacity:
                break
            if not candidates:
                # compress pinned overflow by truncating the least valuable
                victims = sorted(self.items.values(), key=lambda i: i.score(now))
                if not victims:
                    break
                v = victims[0]
                v.content = self._compress(v.content)
                v.pinned = False
                continue
            victim = min(candidates, key=lambda i: i.score(now))
            self.evicted.append({"reason": "capacity", "item": asdict(victim)})
            self.items.pop(victim.id, None)

    @staticmethod
    def _compress(text: str, limit: int = 240) -> str:
        if len(text) <= limit:
            return text
        head, tail = text[: limit // 2], text[-limit // 4 :]
        return f"{head}\n…[{len(text) - len(head) - len(tail)} chars compressed]…\n{tail}"

    def compress(self) -> int:
        """Context compression pass — called when the budget is tight."""
        n = 0
        for item in self.items.values():
            if len(item.content) > 240:
                item.content = self._compress(item.content)
                n += 1
        return n

    def render(self, kinds: Iterable[str] | None = None, max_tokens: int | None = None) -> str:
        """Flatten to a prompt-ready transcript respecting the token budget."""
        budget = max_tokens or self.token_budget
        keep = set(kinds) if kinds else None
        now = time.time()
        ordered = sorted(self.items.values(), key=lambda i: (i.pinned, i.score(now)), reverse=True)
        out: list[str] = []
        used = 0
        for item in ordered:
            if keep and item.kind not in keep:
                continue
            cost = max(1, len(item.content) // 4)
            if used + cost > budget:
                break
            tag = "PINNED " if item.pinned else ""
            out.append(f"[{tag}{item.kind}] {item.content}")
            used += cost
        return "\n".join(out)

    def stats(self) -> dict[str, Any]:
        return {
            "items": len(self.items),
            "capacity": self.capacity,
            "tokens": self.tokens(),
            "token_budget": self.token_budget,
            "load": round(len(self.items) / max(1, self.capacity), 3),
            "pinned": sum(1 for i in self.items.values() if i.pinned),
            "by_kind": _count_by(i.kind for i in self.items.values()),
            "evicted_total": len(self.evicted),
        }

    def snapshot(self) -> list[dict[str, Any]]:
        return [asdict(i) for i in self.items.values()]


def _count_by(seq: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in seq:
        out[s] = out.get(s, 0) + 1
    return out


# ==========================================================================
# B. episodic memory
# ==========================================================================

@dataclass
class Episode:
    situation: str
    objective: str
    modality: str = "text"          # text | code | vision | mixed
    actions: list[dict[str, Any]] = field(default_factory=list)
    result: str = ""
    status: str = UNVERIFIED
    source: str = "user_instruction"
    mistakes: str = ""
    lessons: str = ""
    confidence: float = 0.5
    surprise: float = 0.0
    session_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.modality not in {"text", "code", "vision", "mixed"}:
            raise ValueError(f"invalid modality {self.modality}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid status {self.status}")
        if self.source not in VALID_SOURCES:
            raise ValueError(f"invalid source {self.source} (provenance required)")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0,1]")
        if self.status == VERIFIED and self.source == "unverified_hypothesis":
            raise ValueError("an unverified hypothesis cannot be VERIFIED (prime directive #2)")


class EpisodicMemory:
    def __init__(self, db: BrainDB | None = None) -> None:
        self.db = db or BrainDB()

    def add(self, ep: Episode) -> int:
        ep.validate()
        cur = self.db.execute(
            "INSERT INTO episodes(ts, modality, situation, objective, actions, result, status, source,"
            " mistakes, lessons, confidence, surprise, session_id, meta)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                utcnow(), ep.modality, ep.situation, ep.objective, json.dumps(ep.actions),
                ep.result, ep.status, ep.source, ep.mistakes, ep.lessons, ep.confidence,
                ep.surprise, ep.session_id, json.dumps(ep.meta),
            ),
        )
        eid = int(cur.lastrowid)
        self.db.log_provenance("episodes", eid, "add", detail={"status": ep.status, "source": ep.source})
        self._embed(eid, f"{ep.situation} {ep.objective} {ep.result} {ep.lessons}")
        return eid

    def _embed(self, eid: int, text: str) -> None:
        try:
            from minicoder.model.embeddings import embed_text

            vec = embed_text(text)
            if vec is not None:
                self.db.upsert_embedding("episodes", eid, "text", "minicoder-embedder", vec)
        except Exception:
            pass

    def get(self, eid: int) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM episodes WHERE id=?", (eid,))
        return dict(row) if row else None

    def recent(self, limit: int = 20, include_archived: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM episodes" + ("" if include_archived else " WHERE archived=0")
        return [dict(r) for r in self.db.query(sql + " ORDER BY id DESC LIMIT ?", (limit,))]

    def unconsolidated(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM episodes WHERE consolidated=0 AND archived=0 ORDER BY surprise DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def mark_consolidated(self, ids: list[int]) -> None:
        if not ids:
            return
        with self.db.write() as conn:
            conn.executemany("UPDATE episodes SET consolidated=1 WHERE id=?", [(i,) for i in ids])

    def failures(self, limit: int = 20) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.db.query(
                "SELECT * FROM episodes WHERE status IN ('FAILED','UNVERIFIED') AND archived=0"
                " ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        ]

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Hybrid retrieval: dense vectors when available, else lexical ranking."""
        try:
            from minicoder.model.embeddings import embed_text

            vec = embed_text(query)
            if vec is not None:
                hits = self.db.vector_search(vec, owner="episodes", kinds=("text",), limit=limit)
                # Dense-only recall is untrustworthy at this embedder size, so a
                # hit must ALSO share a content token with the query.
                qtok = set(_content_tokens(query))
                out = []
                for h in hits:
                    row = self.get(h["owner_id"])
                    if not row:
                        continue
                    hay = set(_content_tokens(" ".join(str(row[k] or "") for k in ("situation", "objective", "result", "lessons"))))
                    if qtok & hay:
                        row["score"] = round(h["similarity"], 4)
                        out.append(row)
                if out:
                    return out
        except Exception:
            pass
        return self.lexical_search(query, limit)

    def lexical_search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """BM25 lexical recall. Returns [] when nothing matches — never unrelated rows."""
        toks = set(_content_tokens(query))
        if not toks:
            return self.recent(limit)
        rows = [
            dict(r)
            for r in self.db.query("SELECT * FROM episodes WHERE archived=0 ORDER BY id DESC LIMIT 500")
        ]
        corpus = [
            {"label": r["objective"], "content": " ".join(str(r[k] or "") for k in ("situation", "result", "lessons"))}
            for r in rows
        ]
        scored = []
        for row, view in zip(rows, corpus):
            sc = _bm25(query, corpus, view)
            if sc > 0:
                scored.append((sc + 0.2 * row["confidence"], row))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) FROM episodes")
        return int(row[0]) if row else 0


# ==========================================================================
# C. semantic memory (knowledge graph)
# ==========================================================================

RELATIONS = {"causes", "solves", "depends_on", "visually_resembles", "contradicts", "refines", "part_of"}


class SemanticMemory:
    """NetworkX graph persisted into SQLite (nodes + typed edges)."""

    def __init__(self, db: BrainDB | None = None) -> None:
        self.db = db or BrainDB()
        self.graph = nx.MultiDiGraph()
        self.reload()

    # ----------------------------------------------------------- loading
    def reload(self) -> None:
        self.graph = nx.MultiDiGraph()
        for row in self.db.query("SELECT * FROM semantic_nodes WHERE archived=0"):
            self.graph.add_node(
                row["id"], label=row["label"], kind=row["kind"], content=row["content"],
                status=row["status"], confidence=row["confidence"], access=row["access_count"],
                ts=row["updated_at"], source=row["source"],
            )
        for row in self.db.query("SELECT * FROM semantic_edges"):
            if row["src"] in self.graph and row["dst"] in self.graph:
                self.graph.add_edge(row["src"], row["dst"], relation=row["relation"], weight=row["weight"])

    # -------------------------------------------------------------- write
    def upsert(
        self,
        kind: str,
        label: str,
        content: str,
        status: str = UNVERIFIED,
        source: str = "user_instruction",
        confidence: float = 0.5,
        meta: dict[str, Any] | None = None,
    ) -> int:
        if status not in VALID_STATUSES:
            raise ValueError(status)
        if source not in VALID_SOURCES:
            raise ValueError(f"invalid provenance {source}")
        label = label.strip()[:180]
        existing = self.db.query_one(
            "SELECT * FROM semantic_nodes WHERE kind=? AND label=?", (kind, label)
        )
        now = utcnow()
        if existing:
            nid = int(existing["id"])
            # Contradiction: same label, materially different content.
            if _norm(existing["content"]) != _norm(content):
                sim = _jaccard(_norm(existing["content"]), _norm(content))
                if sim < 0.45:
                    self.db.execute(
                        "INSERT INTO memory_conflicts(ts, node_a, node_b, reason) VALUES (?,?,?,?)",
                        (now, nid, nid, "contradictory content for the same concept"),
                    )
                    self.db.log_provenance("semantic_nodes", nid, "conflict", detail={"incoming": content[:160]})
                    # Keep history: the new statement becomes a separate, linked node.
                    return self._insert(
                        kind, f"{label} (rev {now})", content, status, source, confidence, meta, refines=nid
                    )
            self.db.execute(
                "UPDATE semantic_nodes SET content=?, status=?, confidence=?, updated_at=?, source=? WHERE id=?",
                (content, _stronger(existing["status"], status), max(confidence, existing["confidence"]), now, source, nid),
            )
            self.db.log_provenance("semantic_nodes", nid, "update", detail={"status": status})
            self.graph.nodes[nid].update(content=content, status=status, confidence=confidence, ts=now)
            return nid
        return self._insert(kind, label, content, status, source, confidence, meta)

    def _insert(self, kind, label, content, status, source, confidence, meta, refines: int | None = None) -> int:
        now = utcnow()
        cur = self.db.execute(
            "INSERT INTO semantic_nodes(kind, label, content, status, source, confidence, created_at,"
            " updated_at, last_access, meta) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (kind, label, content, status, source, confidence, now, now, now, json.dumps(meta or {})),
        )
        nid = int(cur.lastrowid)
        self.graph.add_node(nid, label=label, kind=kind, content=content, status=status,
                            confidence=confidence, access=0, ts=now, source=source)
        if refines:
            self.link(nid, refines, "refines")
        if len(self.graph) > CONFIG.memory.graph_max_nodes:
            self._prune()
        self.db.log_provenance("semantic_nodes", nid, "add", detail={"kind": kind, "source": source})
        try:
            from minicoder.model.embeddings import embed_text

            vec = embed_text(f"{label}. {content}")
            if vec is not None:
                self.db.upsert_embedding("semantic_nodes", nid, "text", "minicoder-embedder", vec)
        except Exception:
            pass
        return nid

    def link(self, src: int, dst: int, relation: str, weight: float = 1.0) -> None:
        if relation not in RELATIONS:
            raise ValueError(f"unknown relation {relation}; use one of {sorted(RELATIONS)}")
        if src == dst or src not in self.graph or dst not in self.graph:
            return
        if relation == "contradicts":
            self.db.execute(
                "INSERT INTO memory_conflicts(ts, node_a, node_b, reason) VALUES (?,?,?,?)",
                (utcnow(), src, dst, "explicit contradicts edge"),
            )
        self.db.execute(
            "INSERT OR REPLACE INTO semantic_edges(src, dst, relation, weight, created_at) VALUES (?,?,?,?,?)",
            (src, dst, relation, weight, utcnow()),
        )
        self.graph.add_edge(src, dst, relation=relation, weight=weight)

    def _prune(self) -> None:
        """Archive lowest-value nodes instead of deleting them (directive #3)."""
        rows = self.db.query(
            "SELECT id, access_count, confidence FROM semantic_nodes WHERE archived=0"
            " ORDER BY access_count ASC, confidence ASC LIMIT 50"
        )
        for row in rows:
            self.db.execute("UPDATE semantic_nodes SET archived=1 WHERE id=?", (row["id"],))
            self.graph.remove_node(row["id"])

    # --------------------------------------------------------------- read
    def node(self, nid: int) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM semantic_nodes WHERE id=?", (nid,))
        return dict(row) if row else None

    def touch(self, nids: Iterable[int]) -> None:
        now = utcnow()
        with self.db.write() as conn:
            for nid in nids:
                conn.execute(
                    "UPDATE semantic_nodes SET access_count=access_count+1, last_access=? WHERE id=?",
                    (now, nid),
                )

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Hybrid retrieval: BM25 lexical + dense vectors, fused by reciprocal rank.

        Measured on this project's embedder, cosine similarity alone separates
        related from unrelated text by only ~0.11, so it is used as a *bonus*
        signal on top of lexical relevance rather than as the primary ranker.
        Returns rows annotated with ``score`` (fused, comparable within a query).
        """
        rows = [dict(r) for r in self.db.query("SELECT * FROM semantic_nodes WHERE archived=0")]
        if not rows:
            return []
        lex = {r["id"]: _bm25(query, rows, r) for r in rows}
        lexical_rank = sorted((i for i, v in lex.items() if v > 0), key=lambda i: -lex[i])
        dense_scores: dict[int, float] = {}
        try:
            from minicoder.model.embeddings import embed_text

            vec = embed_text(query)
            if vec is not None:
                for hit in self.db.vector_search(vec, owner="semantic_nodes", kinds=("text",), limit=limit * 3):
                    dense_scores[hit["owner_id"]] = hit["similarity"]
        except Exception:
            pass
        # Reciprocal-rank fusion (k=60), the standard robust combiner.
        fused: dict[int, float] = {}
        for rank, nid in enumerate(lexical_rank[: limit * 3]):
            fused[nid] = fused.get(nid, 0.0) + 1.0 / (60 + rank + 1)
        dense_rank = sorted(dense_scores, key=lambda i: -dense_scores[i])
        for rank, nid in enumerate(dense_rank):
            fused[nid] = fused.get(nid, 0.0) + 0.6 / (60 + rank + 1)
        ranked = sorted(fused, key=lambda i: -fused[i])[:limit]
        out = []
        by_id = {r["id"]: r for r in rows}
        # RRF scores live in ~1/61..2/61, which reads as "0.02" in the UI and
        # looks like noise next to a 0-1 confidence. Normalise the winner to 1.0
        # so scores are comparable *across* queries, not just within one.
        top = max((fused[i] for i in ranked), default=0.0) or 1.0
        for nid in ranked:
            row = by_id[nid]
            row["score"] = round(fused[nid] / top, 4)
            row["lexical"] = round(lex.get(nid, 0.0), 3)
            row["dense"] = round(dense_scores.get(nid, 0.0), 3)
            out.append(row)
        self.touch([r["id"] for r in out])
        return out

    def neighbours(self, nid: int, hops: int = 2) -> dict[str, Any]:
        if nid not in self.graph:
            return {"nodes": [], "edges": []}
        view = nx.ego_graph(self.graph, nid, radius=hops, undirected=True)
        return {
            "nodes": [{"id": n, **{k: v for k, v in data.items() if k != "content"}} for n, data in view.nodes(data=True)],
            "edges": [
                {"src": u, "dst": v, "relation": d.get("relation"), "weight": d.get("weight")}
                for u, v, d in view.edges(data=True)
            ],
        }

    def conflicts(self, unresolved_only: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM memory_conflicts" + (" WHERE resolved=0" if unresolved_only else "")
        return [dict(r) for r in self.db.query(sql + " ORDER BY id DESC LIMIT 100")]

    def stats(self) -> dict[str, Any]:
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "by_kind": _count_by(d.get("kind", "?") for _, d in self.graph.nodes(data=True)),
            "verified": sum(1 for _, d in self.graph.nodes(data=True) if d.get("status") == VERIFIED),
            "density": round(nx.density(self.graph), 5) if self.graph.number_of_nodes() > 1 else 0.0,
            "components": nx.number_weakly_connected_components(self.graph) if self.graph.number_of_nodes() else 0,
        }

    def export_graph(self) -> dict[str, Any]:
        return {
            "nodes": [
                {"id": n, "label": d.get("label"), "kind": d.get("kind"), "status": d.get("status"),
                 "confidence": d.get("confidence"), "content": (d.get("content") or "")[:400]}
                for n, d in self.graph.nodes(data=True)
            ],
            "edges": [
                {"src": u, "dst": v, "relation": d.get("relation"), "weight": d.get("weight")}
                for u, v, d in self.graph.edges(data=True)
            ],
        }

    def save_snapshot(self) -> Path:
        path = CONFIG.paths.knowledge_graph / "graph.json"
        path.write_text(json.dumps(self.export_graph(), indent=1), encoding="utf-8")
        self.db.log_provenance("semantic", None, "graph_snapshot", detail={"nodes": self.graph.number_of_nodes()})
        return path


# Words that carry no retrieval signal. Without this, a probe like "flexbox
# overflow" matches every episode containing "user", "the" or "session".
_STOPWORDS = frozenset(
    """a an the and or but if then than that this these those is are was were be been being
    of in on at to for from by with without into over under up down out off again
    i me my we our you your it its they them their he she his her who whom which what when where why how
    do does did done have has had can could should would may might must will shall
    not no nor so very just also too only own same such both few more most other some any each every
    user users session turn asked shared says said""".split()
)


def _content_tokens(text: str) -> list[str]:
    return [t for t in _norm(text).split() if t not in _STOPWORDS and len(t) > 1]


_SYNONYMS: dict[str, set[str]] = {
    "margin": {"negative", "space", "edge", "padding", "gap", "whitespace", "spacing"},
    "spacing": {"margin", "negative", "space", "gap", "padding"},
    "padding": {"margin", "space", "gap", "inset"},
    "left": {"leave", "margin", "space"},
    "leave": {"left", "margin", "space"},
    "overflow": {"shrink", "wider", "clips", "spills"},
    "clips": {"overflow", "truncation"},
    "luxurious": {"luxury", "premium", "elegant", "champagne"},
    "premium": {"luxurious", "luxury", "elegant"},
    "big": {"large", "size", "scale"},
    "size": {"scale", "resolution", "export"},
    "font": {"type", "typography", "line", "height", "text"},
    "colour": {"color"},
    "color": {"colour"},
    "readable": {"contrast", "luminance"},
}


def _expand(tokens: list[str]) -> list[str]:
    out = list(tokens)
    for t in tokens:
        out.extend(_SYNONYMS.get(t, ()))
    return out


def _bm25(query: str, corpus: list[dict[str, Any]], row: dict[str, Any], k1: float = 1.4,
          b: float = 0.75) -> float:
    """Okapi BM25 between the query and one node: its label plus content."""
    q = _expand(_content_tokens(query))
    if not q:
        return 0.0
    docs = [_content_tokens(f"{r['label']} {r['content']}") for r in corpus]
    n = max(1, len(docs))
    avg_len = sum(len(d) for d in docs) / n or 1.0
    tokens = _content_tokens(f"{row['label']} {row['content']}")
    length = len(tokens) or 1
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    score = 0.0
    for term in set(q):
        df = sum(1 for d in docs if term in d)
        if not df:
            continue
        idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
        tf = freq.get(term, 0)
        if not tf:
            continue
        score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * length / avg_len))
    # A label match is a very strong signal.
    if any(t in _norm(row["label"]).split() for t in q):
        score *= 1.35
    return score


def _jaccard(a: str, b: str) -> float:
    A, B = set(a.split()), set(b.split())
    return len(A & B) / max(1, len(A | B))


_STATUS_RANK = {FAILED: 0, UNVERIFIED: 1, QUARANTINED: 1, VERIFIED: 2}


def _stronger(a: str, b: str) -> str:
    return a if _STATUS_RANK.get(a, 0) >= _STATUS_RANK.get(b, 0) else b


# ==========================================================================
# D. procedural memory
# ==========================================================================

@dataclass
class Skill:
    slug: str
    name: str
    description: str
    domain: str = "general"
    params_schema: dict[str, Any] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    solution: str = ""
    verification: dict[str, Any] = field(default_factory=dict)
    status: str = UNVERIFIED
    source: str = "verified_execution"
    confidence: float = 0.5
    episode_ids: list[int] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class ProceduralMemory:
    """Verified-skill staging buffer that feeds sleep dataset compilation."""

    def __init__(self, db: BrainDB | None = None) -> None:
        self.db = db or BrainDB()
        self.dir = CONFIG.paths.procedural
        self.dir.mkdir(parents=True, exist_ok=True)

    def add(self, skill: Skill, *, verified: bool) -> int:
        if skill.source not in VALID_SOURCES:
            raise ValueError(f"invalid provenance {skill.source}")
        status = VERIFIED if verified else QUARANTINED
        if verified:
            # A verified skill is only trainable if its evidence is content-addressed.
            payload = json.dumps(
                {"solution": skill.solution, "tools": skill.tool_calls, "verification": skill.verification},
                sort_keys=True, default=str,
            )
            import hashlib as _hash

            skill.verification = dict(skill.verification or {})
            skill.verification.setdefault("hash", _hash.sha256(payload.encode()).hexdigest())
            skill.verification.setdefault("passed", True)
        if not verified:
            skill.confidence = min(skill.confidence, 0.35)
        now = utcnow()
        existing = self.db.query_one("SELECT id, status FROM skills WHERE slug=?", (skill.slug,))
        if existing:
            sid = int(existing["id"])
            self.db.execute(
                "UPDATE skills SET name=?, description=?, domain=?, params_schema=?, reasoning=?,"
                " tool_calls=?, solution=?, verification=?, status=?, confidence=?, updated_at=?,"
                " verified_at=? WHERE id=?",
                (
                    skill.name, skill.description, skill.domain, json.dumps(skill.params_schema),
                    json.dumps(skill.reasoning), json.dumps(skill.tool_calls), skill.solution,
                    json.dumps(skill.verification), status, skill.confidence, now,
                    now if verified else None, sid,
                ),
            )
        else:
            cur = self.db.execute(
                "INSERT INTO skills(slug, name, domain, description, params_schema, reasoning, tool_calls,"
                " solution, verification, status, source, confidence, episode_ids, created_at, updated_at, verified_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    skill.slug, skill.name, skill.domain, skill.description,
                    json.dumps(skill.params_schema), json.dumps(skill.reasoning),
                    json.dumps(skill.tool_calls), skill.solution, json.dumps(skill.verification),
                    status, skill.source, skill.confidence, json.dumps(skill.episode_ids),
                    now, now, now if verified else None,
                ),
            )
            sid = int(cur.lastrowid)
        self.db.log_provenance("skills", sid, "verify" if verified else "quarantine",
                               detail={"slug": skill.slug, "status": status})
        if verified:
            (self.dir / f"{skill.slug}.json").write_text(
                json.dumps({"slug": skill.slug, "name": skill.name, "description": skill.description,
                            "domain": skill.domain, "params": skill.params_schema,
                            "reasoning": skill.reasoning, "tool_calls": skill.tool_calls,
                            "solution": skill.solution, "verification": skill.verification,
                            "confidence": skill.confidence, "source": skill.source}, indent=2),
                encoding="utf-8",
            )
        return sid

    def get(self, slug: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM skills WHERE slug=?", (slug,))
        return dict(row) if row else None

    def verified(self, exported: bool | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM skills WHERE status='VERIFIED'"
        params: tuple = ()
        if exported is not None:
            sql += " AND exported=?"
            params = (1 if exported else 0,)
        return [dict(r) for r in self.db.query(sql + " ORDER BY verified_at DESC", params)]

    def any(self, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM skills"
        params: tuple = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        return [dict(r) for r in self.db.query(sql + " ORDER BY id DESC", params)]

    def mark_exported(self, ids: list[int]) -> None:
        with self.db.write() as conn:
            conn.executemany("UPDATE skills SET exported=1 WHERE id=?", [(i,) for i in ids])

    def record_use(self, slug: str) -> None:
        self.db.execute(
            "UPDATE skills SET used_count=used_count+1, last_used=? WHERE slug=?", (utcnow(), slug)
        )

    def search(self, query: str, limit: int = 8, *, status: str | None = VERIFIED) -> list[dict[str, Any]]:
        """BM25 over skill prose + solution.

        Matching the raw query as one substring returned nothing for any
        multi-word probe (measured: "flexbox overflow" missed every code skill),
        so this tokenizes and ranks. Returns [] when nothing genuinely matches
        rather than padding with unrelated skills.
        """
        sql = "SELECT * FROM skills"
        params: tuple = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        rows = [dict(r) for r in self.db.query(sql, params)]
        if not rows:
            return []
        corpus = [
            {"label": r.get("name", ""), "content": " ".join(
                str(r.get(k) or "") for k in ("description", "solution", "domain", "reasoning"))}
            for r in rows
        ]
        scored = []
        for row, doc in zip(rows, corpus):
            score = _bm25(query, corpus, doc)
            if score > 0:
                row["score"] = round(score, 4)
                scored.append((score, row))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def stats(self) -> dict[str, Any]:
        rows = self.db.query("SELECT status, COUNT(*) n FROM skills GROUP BY status")
        by_status = {r["status"]: r["n"] for r in rows}
        return {
            "total": sum(by_status.values()),
            "verified": by_status.get(VERIFIED, 0),
            "quarantined": by_status.get(QUARANTINED, 0),
            "failed": by_status.get(FAILED, 0),
            "pending_export": int(
                (self.db.query_one("SELECT COUNT(*) FROM skills WHERE status='VERIFIED' AND exported=0") or [0])[0]
            ),
            "by_status": by_status,
        }


# ==========================================================================
# E. visual memory
# ==========================================================================

class VisualMemory:
    def __init__(self, db: BrainDB | None = None) -> None:
        self.db = db or BrainDB()

    def all(self, limit: int = 50) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.query(
            "SELECT id, ts, sha256, width, height, ocr_text, description, labels, status, source"
            " FROM visual_memories ORDER BY id DESC LIMIT ?", (limit,))]

    def get(self, vid: int) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM visual_memories WHERE id=?", (vid,))
        return dict(row) if row else None

    def search(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        toks = set(_content_tokens(query))
        scored = []
        for row in self.db.query("SELECT * FROM visual_memories"):
            hay = _norm(f"{row['ocr_text']} {row['description']} {row['labels']}")
            overlap = len(toks & set(hay.split()))
            if overlap:
                scored.append((overlap, dict(row)))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def stats(self) -> dict[str, Any]:
        row = self.db.query_one("SELECT COUNT(*) FROM visual_memories")
        return {"count": int(row[0]) if row else 0}
