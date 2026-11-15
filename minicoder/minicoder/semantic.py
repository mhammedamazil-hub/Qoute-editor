"""Semantic memory — persistent knowledge graph.

Concepts and relations live in SQLite (durable, queryable). A NetworkX
MultiDiGraph is materialised on demand for traversal (multi-hop neighbourhood,
shortest path, neighbourhood summaries) and snapshotted to JSON after sleep.
"""
from __future__ import annotations
import json
import networkx as nx
from .config import get_settings
from .db import connect, log_provenance
from .util import new_id, now_iso, utcnow_compact
from .embeddings import embed_text
from . import vecstore

RELATIONS = {"causes", "solves", "depends_on", "visually_resembles",
             "related_to", "contradicts", "part_of", "fixes", "prevents"}


def add_concept(label: str, *, kind: str = "concept", confidence: float = 0.5,
                source: str = "user_instruction", meta: dict | None = None) -> str:
    label = " ".join(label.strip().split())
    if not label:
        raise ValueError("concept label must not be empty")
    with connect() as con:
        row = con.execute("SELECT id FROM concepts WHERE lower(label)=lower(?) AND archived=0",
                          (label,)).fetchone()
        if row:
            con.execute("UPDATE concepts SET confidence=MAX(confidence, ?), updated_at=? WHERE id=?",
                        (confidence, now_iso(), row["id"]))
            return row["id"]
        cid = new_id("concept")
        con.execute(
            "INSERT INTO concepts(id, label, kind, confidence, source, created_at, updated_at, archived, meta_json)"
            " VALUES (?,?,?,?,?,?,?,0,?)",
            (cid, label, kind, confidence, source, now_iso(), now_iso(), json.dumps(meta or {})),
        )
        vecstore.embed_and_store(con, cid, "concept", label)
        log_provenance(con, "concept", cid, source, kind)
        return cid


def add_relation(src_label: str, dst_label: str, relation: str, *,
                 confidence: float = 0.5, source: str = "user_instruction",
                 meta: dict | None = None) -> tuple[str, str]:
    relation = relation.strip().lower()
    if relation not in RELATIONS:
        raise ValueError(f"unknown relation '{relation}'. Allowed: {sorted(RELATIONS)}")
    src = add_concept(src_label, source=source, confidence=confidence)
    dst = add_concept(dst_label, source=source, confidence=confidence)
    with connect() as con:
        con.execute(
            "INSERT INTO relations(src, dst, relation, confidence, source, created_at, meta_json)"
            " VALUES (?,?,?,?,?,?,?) ON CONFLICT(src, dst, relation) DO UPDATE SET"
            " confidence=MAX(relations.confidence, excluded.confidence)",
            (src, dst, relation, confidence, source, now_iso(), json.dumps(meta or {})),
        )
    return src, dst


def load_graph() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    with connect() as con:
        for r in con.execute("SELECT * FROM concepts WHERE archived=0").fetchall():
            g.add_node(r["id"], label=r["label"], kind=r["kind"],
                       confidence=r["confidence"], source=r["source"])
        for r in con.execute("SELECT * FROM relations").fetchall():
            if g.has_node(r["src"]) and g.has_node(r["dst"]):
                g.add_edge(r["src"], r["dst"], key=r["relation"], relation=r["relation"],
                           confidence=r["confidence"], source=r["source"])
    return g


def neighbourhood(label: str, *, depth: int = 2, limit: int = 60) -> dict:
    """Multi-hop traversal from a concept (case-insensitive substring match)."""
    with connect() as con:
        row = con.execute(
            "SELECT id, label FROM concepts WHERE archived=0 AND lower(label) LIKE lower(?) LIMIT 1",
            (f"%{label.strip()}%",)).fetchone()
    if row is None:
        return {"found": False, "query": label, "nodes": [], "edges": []}
    g = load_graph()
    ego = nx.ego_graph(g, row["id"], radius=depth, undirected=True)
    nodes = [{"id": n, **g.nodes[n]} for n in list(ego.nodes)[:limit]]
    edges = [{"src": u, "dst": v, "relation": d.get("relation", k), "confidence": d.get("confidence", 0.5)}
             for u, v, k, d in list(ego.edges(keys=True, data=True))[:limit * 2]]
    return {"found": True, "root": {"id": row["id"], "label": row["label"]},
            "nodes": nodes, "edges": edges}


def graph_payload(limit: int = 200) -> dict:
    """Compact node/edge dump for the dashboard."""
    g = load_graph()
    nodes = [{"id": n, **g.nodes[n]} for n in list(g.nodes)[:limit]]
    keep = {n["id"] for n in nodes}
    edges = [{"src": u, "dst": v, "relation": d.get("relation", k),
              "confidence": round(float(d.get("confidence", 0.5)), 3)}
             for u, v, k, d in list(g.edges(keys=True, data=True))
             if u in keep and v in keep][: limit * 3]
    return {"nodes": nodes,"edges": edges, "total_nodes": g.number_of_nodes(),
            "total_edges": g.number_of_edges()}


def snapshot_graph() -> str:
    settings = get_settings()
    settings.graph_dir.mkdir(parents=True, exist_ok=True)
    g = load_graph()
    payload = {
        "saved_at": now_iso(),
        "nodes": [{"id": n, **g.nodes[n]} for n in g.nodes],
        "edges": [{"src": u, "dst": v, **d} for u, v, _, d in g.edges(keys=True, data=True)],
    }
    out = settings.graph_dir / f"graph_{utcnow_compact()}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(out)


def search_concepts(query: str, *, top_k: int = 8) -> list[tuple[dict, float]]:
    from .embeddings import embed_text, from_blob
    from .vecstore import _search_numpy
    q = embed_text(query)
    with connect() as con:
        hits = _search_numpy(con, q, "concept", top_k) if top_k else []
        # prefer sqlite-vec path if available
        try:
            from .vecstore import search_vectors
            hits = search_vectors(con, q, kind="concept", top_k=top_k)
        except Exception:
            pass
        out = []
        for cid, score in hits:
            row = con.execute("SELECT * FROM concepts WHERE id=? AND archived=0", (cid,)).fetchone()
            if row:
                out.append((dict(row), score))
        return out


def conflicts() -> list[dict]:
    """Concept pairs linked by 'contradicts' — surfacing, never auto-resolving."""
    with connect() as con:
        rows = con.execute(
            "SELECT a.label AS src, b.label AS dst, r.confidence, r.source "
            "FROM relations r JOIN concepts a ON a.id=r.src JOIN concepts b ON b.id=r.dst "
            "WHERE r.relation='contradicts' ORDER BY r.created_at DESC").fetchall()
        return [dict(r) for r in rows]
