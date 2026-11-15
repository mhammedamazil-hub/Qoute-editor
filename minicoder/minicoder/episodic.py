"""Episodic memory — timestamped, provenance-carrying autobiographical record."""
from __future__ import annotations
import json
from . import vecstore
from .config import get_settings
from .db import connect, log_provenance
from .embeddings import embed_text
from .models import Episode
from .util import new_id, now_iso


def _row_to_episode(r) -> Episode:
    return Episode(
        id=r["id"], situation=r["situation"], modality=r["modality"],
        objective=r["objective"], actions=json.loads(r["actions_json"]),
        result=r["result"], verification_status=r["verification_status"],
        mistakes=json.loads(r["mistakes_json"]), lessons=json.loads(r["lessons_json"]),
        source=r["source"], confidence=r["confidence"], access_count=r["access_count"],
        created_at=r["created_at"], updated_at=r["updated_at"],
        archived=bool(r["archived"]), tags=json.loads(r["tags_json"]),
        meta=json.loads(r["meta_json"]),
    )


def record_episode(*, situation: str, modality: str = "text", objective: str = "",
                   actions: list[str] | None = None, result: str = "",
                   verification_status: str = "UNVERIFIED",
                   mistakes: list[str] | None = None, lessons: list[str] | None = None,
                   source: str = "user_instruction", confidence: float = 0.5,
                   tags: list[str] | None = None, meta: dict | None = None) -> Episode:
    settings = get_settings()
    settings.ensure_dirs()
    ep = Episode(
        id=new_id("ep"), situation=situation.strip(), modality=modality, objective=objective,
        actions=actions or [], result=result, verification_status=verification_status,
        mistakes=mistakes or [], lessons=lessons or [], source=source,
        confidence=confidence, access_count=0, created_at=now_iso(), updated_at=now_iso(),
        archived=False, tags=tags or [], meta=meta or {},
    )
    with connect() as con:
        con.execute(
            "INSERT INTO episodes(id, situation, modality, objective, actions_json, result,"
            " verification_status, mistakes_json, lessons_json, source, confidence, access_count,"
            " created_at, updated_at, archived, tags_json, meta_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
            (ep.id, ep.situation, ep.modality, ep.objective, json.dumps(ep.actions), ep.result,
             ep.verification_status, json.dumps(ep.mistakes), json.dumps(ep.lessons), ep.source,
             ep.confidence, ep.access_count, ep.created_at, ep.updated_at,
             json.dumps(ep.tags), json.dumps(ep.meta)),
        )
        vecstore.embed_and_store(con, ep.id, "episode",
                                 f"{ep.situation}\n{ep.objective}\n{ep.result}\n{' '.join(ep.lessons)}")
        log_provenance(con, "episode", ep.id, ep.source, f"status={ep.verification_status}")
    return ep


def get_episode(episode_id: str, *, touch: bool = True) -> Episode | None:
    with connect() as con:
        row = con.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()
        if row is None:
            return None
        if touch:
            con.execute("UPDATE episodes SET access_count=access_count+1, updated_at=? WHERE id=?",
                        (now_iso(), episode_id))
            row = con.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()
        return _row_to_episode(row)


def list_episodes(*, limit: int = 20, include_archived: bool = False,
                  status: str | None = None) -> list[Episode]:
    sql = "SELECT * FROM episodes"
    clauses, params = [], []
    if not include_archived:
        clauses.append("archived=0")
    if status:
        clauses.append("verification_status=?")
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with connect() as con:
        return [_row_to_episode(r) for r in con.execute(sql, params).fetchall()]


def search_episodes(query: str, *, top_k: int = 6, include_archived: bool = False) -> list[tuple[Episode, float]]:
    """Semantic-ish retrieval: vector cosine fused with FTS5 keyword score."""
    settings = get_settings()
    q_vec = embed_text(query)
    with connect() as con:
        vec_hits = dict(vecstore.search_vectors(con, q_vec, kind="episode", top_k=top_k * 3))
        fts_rows = []
        try:
            fts_rows = con.execute(
                "SELECT rowid, bm25(episodes_fts) AS score FROM episodes_fts WHERE episodes_fts MATCH ? LIMIT ?",
                (_fts_query(query), top_k * 3)).fetchall()
        except Exception:
            fts_rows = []
        fts_scores: dict[int, float] = {}
        for r in fts_rows:
            fts_scores[r["rowid"]] = -float(r["score"])  # bm25 returns lower=better
        # map rowid → episode id
        rowid_to_id: dict[int, str] = {}
        if fts_scores:
            qmarks = ",".join("?" for _ in fts_scores)
            for r in con.execute(f"SELECT rowid, id FROM episodes WHERE rowid IN ({qmarks})",
                                 list(fts_scores)).fetchall():
                rowid_to_id[r["rowid"]] = r["id"]
        merged: dict[str, float] = {}
        if vec_hits:
            vmax = max(vec_hits.values()) or 1.0
            for eid, score in vec_hits.items():
                merged[eid] = max(merged.get(eid, 0.0), 0.75 * (score / vmax if vmax > 0 else 0.0))
        if fts_scores and rowid_to_id:
            fmax = max(fts_scores.values()) or 1.0
            for rid, score in fts_scores.items():
                eid = rowid_to_id.get(rid)
                if eid:
                    merged[eid] = max(merged.get(eid, 0.0), 0.55 * (score / fmax if fmax > 0 else 0.0))
        if not merged:
            return []
        ranked = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        out: list[tuple[Episode, float]] = []
        for eid, score in ranked:
            row = con.execute("SELECT * FROM episodes WHERE id=?", (eid,)).fetchone()
            if row is None:
                continue
            if not include_archived and row["archived"]:
                continue
            out.append((_row_to_episode(row), round(float(score), 4)))
        return out


def mark_verified(episode_id: str, *, confidence: float | None = None) -> None:
    with connect() as con:
        if confidence is None:
            con.execute("UPDATE episodes SET verification_status='VERIFIED', updated_at=? WHERE id=?",
                        (now_iso(), episode_id))
        else:
            con.execute("UPDATE episodes SET verification_status='VERIFIED', confidence=?, updated_at=? WHERE id=?",
                        (confidence, now_iso(), episode_id))
        log_provenance(con, "episode", episode_id, "verified_execution", "marked VERIFIED")


def mark_failed(episode_id: str, *, reason: str = "") -> None:
    with connect() as con:
        con.execute("UPDATE episodes SET verification_status='FAILED', updated_at=? WHERE id=?",
                    (now_iso(), episode_id))
        log_provenance(con, "episode", episode_id, "verified_execution", f"FAILED: {reason}")


def archive_episodes(episode_ids: list[str]) -> int:
    if not episode_ids:
        return 0
    with connect() as con:
        qmarks = ",".join("?" for _ in episode_ids)
        con.execute(f"UPDATE episodes SET archived=1, updated_at=? WHERE id IN ({qmarks})",
                    [now_iso(), *episode_ids])
        return len(episode_ids)


def _fts_query(query: str) -> str:
    from .util import tokenize
    toks = tokenize(query)[:12]
    if not toks:
        return '"cognitive"'
    return " OR ".join(f'"{t}"' for t in toks)
