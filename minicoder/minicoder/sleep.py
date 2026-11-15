"""The Sleep Engine — seven stages, exactly as the blueprint specifies.

Triggers: brain.sleep() (user), idle threshold (CLI/API scheduler), scheduled
maintenance, or episodic capacity pressure. Interactive generation pauses for
the duration. A full SQLite backup is taken before anything is mutated.
"""
from __future__ import annotations
import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from .config import get_settings
from .db import backup_db, connect, get_meta, set_meta, init_db
from .episodic import record_episode  # noqa: F401  (re-exported convenience)
from .models import SleepReport, VerificationStep
from .semantic import add_concept, add_relation, snapshot_graph, conflicts
from .util import atomic_write_json, new_id, now_iso, utcnow_compact, content_hash
from . import episodic as episodic_mod
from . import procedural as procedural_mod
from . import shard as shard_mod


def _parse_iso(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _recency_weight(created_iso: str, half_life_days: float) -> float:
    age_days = max(0.0, (datetime.now(timezone.utc) - _parse_iso(created_iso)).total_seconds() / 86400.0)
    return 0.5 ** (age_days / max(0.1, half_life_days))


# ------------------------------------------------------------- stage 1: replay
def stage_replay(con, *, last_sleep: str | None, limit: int = 50) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM episodes WHERE archived=0 "
        + ("AND created_at > ? " if last_sleep else "")
        + "ORDER BY created_at DESC LIMIT 200",
        ((last_sleep,) if last_sleep else ()),
    ).fetchall()
    ranked = []
    for r in rows:
        surprise = 1.0 - float(r["confidence"])
        failure_bonus = 0.35 if r["verification_status"] in ("FAILED", "UNVERIFIED") else 0.0
        mistakes = json.loads(r["mistakes_json"])
        mistake_bonus = min(0.2, 0.1 * len(mistakes))
        score = surprise + failure_bonus + mistake_bonus
        ranked.append({"id": r["id"], "score": round(score, 4),
                       "status": r["verification_status"], "modality": r["modality"],
                       "created_at": r["created_at"], "situation": r["situation"][:200]})
    ranked.sort(key=lambda e: e["score"], reverse=True)
    return ranked[:limit]


# ------------------------------------------------------ stage 2: consolidation
def stage_consolidate(con, replay: list[dict]) -> dict:
    lessons, linked, merged = 0, 0, 0
    seen_hashes: dict[str, str] = {}
    for item in replay:
        row = con.execute("SELECT * FROM episodes WHERE id=?", (item["id"],)).fetchone()
        if row is None:
            continue
        # dedup by normalised situation
        key = content_hash(" ".join(row["situation"].lower().split())[:400])
        if key in seen_hashes:
            keeper, dupe = seen_hashes[key], row["id"]
            con.execute(
                "UPDATE episodes SET archived=1, meta_json=json_set(meta_json,'$.merged_into',?), updated_at=? WHERE id=?",
                (keeper, now_iso(), dupe))
            merged += 1
            continue
        seen_hashes[key] = row["id"]
        episode_lessons = json.loads(row["lessons_json"])
        mistakes = json.loads(row["mistakes_json"])
        tags = json.loads(row["tags_json"])
        extracted = list(episode_lessons)
        if row["verification_status"] == "VERIFIED" and row["result"]:
            extracted.append(f"Verified outcome worth reusing: {row['result'][:200]}")
        for m in mistakes:
            extracted.append(f"Avoid: {m}")
        if not extracted and row["verification_status"] == "FAILED":
            extracted.append(f"Failure to investigate: {row['situation'][:160]}")
        new_conf = {"VERIFIED": 0.85, "FAILED": 0.35}.get(row["verification_status"], 0.5)
        if extracted:
            con.execute("UPDATE episodes SET lessons_json=?, confidence=MAX(confidence, ?), updated_at=? WHERE id=?",
                        (json.dumps(sorted(set(extracted))), new_conf, now_iso(), row["id"]))
            lessons += len(extracted)
        for tag in tags[:6]:
            add_concept(tag, kind="concept", confidence=new_conf,
                        source="verified_execution" if row["verification_status"] == "VERIFIED" else "unverified_hypothesis")
            linked += 1
    return {"lessons": lessons, "linked": linked, "merged": merged}


# -------------------------------------------- stage 3: cross-modal patterns
def stage_patterns(con, *, last_sleep: str | None) -> list[str]:
    rows = con.execute(
        "SELECT modality, tags_json, verification_status FROM episodes WHERE archived=0"
        + (" AND created_at > ?" if last_sleep else ""),
        ((last_sleep,) if last_sleep else ())).fetchall()
    buckets: dict[str, list[str]] = {}
    for r in rows:
        for tag in json.loads(r["tags_json"]):
            buckets.setdefault(tag.lower(), []).append(r["verification_status"])
    patterns = []
    for tag, statuses in buckets.items():
        if len(statuses) >= 3:
            fails = statuses.count("FAILED")
            ratio = fails / len(statuses)
            if ratio > 0.5:
                patterns.append(
                    f"Recurring failure pattern across {len(statuses)} episodes tagged '{tag}' "
                    f"({fails} FAILED). Correlation only — causation requires a verified fix; "
                    f"treat as a hypothesis, not a fact.")
            elif fails == 0:
                patterns.append(
                    f"Reliable success pattern: {len(statuses)} episodes tagged '{tag}' all passed verification.")
    return patterns


# --------------------------------------- stage 4: organization & conflicts
def stage_organize(con) -> dict:
    # merge duplicate concept labels (normalised) — keep highest confidence
    dupes = con.execute(
        "SELECT lower(label) AS k, COUNT(*) c FROM concepts WHERE archived=0 "
        "GROUP BY lower(label) HAVING c > 1").fetchall()
    merged = 0
    for d in dupes:
        rows = con.execute("SELECT * FROM concepts WHERE lower(label)=? ORDER BY confidence DESC",
                           (d["k"],)).fetchall()
        keeper = rows[0]
        for dupe in rows[1:]:
            con.execute("UPDATE relations SET src=? WHERE src=?", (keeper["id"], dupe["id"]))
            con.execute("UPDATE relations SET dst=? WHERE dst=?", (keeper["id"], dupe["id"]))
            con.execute("UPDATE concepts SET archived=1, meta_json=json_set(meta_json,'$.merged_into',?), updated_at=? WHERE id=?",
                        (keeper["id"], now_iso(), dupe["id"]))
            merged += 1
    conflict_list = conflicts()
    return {"concepts_merged": merged, "conflicts": len(conflict_list),
            "conflict_detail": conflict_list[:10]}


# ----------------------------- stage 5: forgetting & compression (decay fn)
def stage_forget(con, *, half_life_days: float, archive_threshold: float) -> dict:
    rows = con.execute("SELECT id, confidence, access_count, created_at FROM episodes WHERE archived=0").fetchall()
    evict_ids = []
    for r in rows:
        recency = _recency_weight(r["created_at"], half_life_days)
        usefulness = 0.5 + 0.5 * min(1.0, (r["access_count"] or 0) / 5.0)
        score = float(r["confidence"]) * 0.4 + recency * 0.45 * usefulness + min(1.0, (r["access_count"] or 0) / 10.0) * 0.15
        if score < archive_threshold:
            evict_ids.append((r["id"], score))
    if not evict_ids:
        return {"archived": 0, "archive_file": None}
    settings = get_settings()
    ts = utcnow_compact()
    archive_file = settings.archived_dir / f"archive_{ts}.jsonl"
    with connect() as w:
        with archive_file.open("w", encoding="utf-8") as fh:
            for eid, score in evict_ids:
                row = w.execute("SELECT * FROM episodes WHERE id=?", (eid,)).fetchone()
                if row:
                    obj = dict(row)
                    obj["decay_score"] = round(score, 4)
                    fh.write(json.dumps(obj, default=str) + "\n")
            qmarks = ",".join("?" for _ in evict_ids)
            w.execute(f"UPDATE episodes SET archived=1, updated_at=? WHERE id IN ({qmarks})",
                      [now_iso(), *[e for e, _ in evict_ids]])
    return {"archived": len(evict_ids), "archive_file": str(archive_file)}


# ------ stage 6: skill compilation + weakness repair (sandbox re-verification)
def stage_compile(con, *, last_sleep: str | None, patterns: list[str]) -> dict:
    skills = procedural_mod.verified_skills_since(last_sleep)
    shard_summary = None
    if skills:
        shard_summary = shard_mod.compile_shard(skills)
    # weakness repair: FAILED episodes carrying retest material are re-run for real
    reverified = 0
    rows = con.execute(
        "SELECT id, meta_json FROM episodes WHERE archived=0 AND verification_status='FAILED' "
        "AND meta_json LIKE '%sandbox_retest%'").fetchall()
    from .tools.coding import verify_python_solution
    for r in rows:
        try:
            meta = json.loads(r["meta_json"])
            retest = meta.get("sandbox_retest") or {}
            solution, tests = retest.get("solution"), retest.get("tests")
            if not solution or not tests:
                continue
            steps = verify_python_solution(solution=solution, tests=tests)
            if all(s.passed for s in steps):
                con.execute("UPDATE episodes SET verification_status='VERIFIED', confidence=0.8, updated_at=?, "
                            "meta_json=json_set(meta_json,'$.repair','reverified_during_sleep') WHERE id=?",
                            (now_iso(), r["id"]))
                reverified += 1
        except Exception:
            continue
    weaknesses = []
    for p in patterns:
        if "failure pattern" in p:
            weaknesses.append(p.split("tagged ")[1].split("'")[1] if "tagged " in p else "unknown")
    return {"skills": skills, "shard": shard_summary, "reverified": reverified,
            "weakness_domains": weaknesses}


# --------- stage 7: GitHub dispatch, adapter check, indexes, sleep report
def stage_dispatch(con, *, shard_summary: dict | None, report: SleepReport, trigger: str) -> dict:
    settings = get_settings()
    notes: list[str] = []
    dispatch = "not_configured"
    if shard_summary:
        shard_path = Path(shard_summary["shard_path"])
        if not settings.github_dispatch:
            dispatch = "pending_dispatch"
            rel = shard_path
            try:
                rel = shard_path.relative_to(_repo_root())
            except ValueError:
                pass
            notes.append(f"Skill shard compiled at {shard_path} and left for you to review. "
                         f"To auto-publish a PR and trigger CI, set MINICODER_GITHUB_DISPATCH=1 "
                         f"(or just `git add {rel} && git push` on a branch).")
            snapshot_path = snapshot_graph()
            set_meta(con, "last_sleep_shard", shard_summary["shard_path"] if shard_summary else "")
            return {"dispatch": dispatch, "notes": notes, "graph_snapshot": snapshot_path}
        try:
            result = _git_push_shard(shard_path)
            dispatch = result
        except FileNotFoundError:
            dispatch = "pending_dispatch"
            notes.append("git/gh CLI not available or no remote configured — shard saved locally; "
                         "push to datasets/sleep_skills/ to trigger the GitHub training workflow.")
        except subprocess.CalledProcessError as e:
            dispatch = "failed"
            notes.append(f"git/gh dispatch failed honestly (exit {e.returncode}): "
                         f"{(e.stderr or e.stdout or '')[:300] if hasattr(e, 'stderr') else e}")
    else:
        notes.append("No newly VERIFIED skills since last sleep — nothing to compile.")
    # adapter release check (never fabricated — only if gh works)
    adapter_note = _check_adapter_release()
    if adapter_note:
        notes.append(adapter_note)
    snapshot_path = snapshot_graph()
    set_meta(con, "last_sleep_shard", shard_summary["shard_path"] if shard_summary else "")
    return {"dispatch": dispatch, "notes": notes, "graph_snapshot": snapshot_path}


def _git_push_shard(shard_path: Path) -> str:
    """Commit the shard on a dedicated branch and open a PR via gh.

    Uses a throwaway `git worktree` under memory/ so the user's working tree
    and current branch are NEVER switched, even if something fails."""
    import shutil
    import uuid
    if not (shutil.which("git") and shutil.which("gh")):
        raise FileNotFoundError("git or gh CLI not found")
    repo = _repo_root()
    settings = get_settings()
    ts = utcnow_compact()
    branch = f"sleep/skills-{ts}"
    wt = settings.home / f"wt-{ts}-{uuid.uuid4().hex[:6]}"
    subprocess.run(["git", "fetch", "origin", "main", "--quiet"],
                   cwd=repo, check=True, capture_output=True, timeout=120)
    subprocess.run(["git", "worktree", "add", "-b", branch, str(wt), "origin/main", "--quiet"],
                   cwd=repo, check=True, capture_output=True, timeout=120)
    try:
        dest_dir = wt / "datasets" / "sleep_skills"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / shard_path.name
        shutil.copy2(shard_path, dest)
        # also publish the manifest so CI can diff totals
        manifest = shard_path.parent / "manifest.json"
        if manifest.exists():
            shutil.copy2(manifest, dest_dir / "manifest.json")
        subprocess.run(["git", "add", "datasets/sleep_skills"], cwd=wt,
                       check=True, capture_output=True)
        status = subprocess.run(["git", "status", "--porcelain"], cwd=wt,
                               check=True, capture_output=True, text=True)
        if not status.stdout.strip():
            return "nothing_to_commit"
        subprocess.run(["git", "commit", "-m", f"sleep: compile verified skills → {shard_path.name}"],
                       cwd=wt, check=True, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", branch], cwd=wt,
                       check=True, capture_output=True, timeout=180)
        subprocess.run(["gh", "pr", "create",
                        "--title", f"Sleep: skill dataset {shard_path.name}",
                        "--body",
                        "Automated skill-shard PR opened by MiniCoder's sleep engine. "
                        "The `sleep_skill_training` workflow validates the shard, trains "
                        "(if the CI gate passes) and publishes the adapter release. "
                        "Unverified skills are never included."],
                       cwd=wt, check=True, capture_output=True, timeout=120)
        return "dispatched"
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                       cwd=repo, check=False, capture_output=True, timeout=120)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _check_adapter_release() -> str | None:
    import shutil
    if not shutil.which("gh"):
        return None
    try:
        out = subprocess.run(["gh", "release", "list", "--limit", "3"],
                             cwd=_repo_root(), capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            return None
        lines = [l for l in out.stdout.splitlines() if l.strip()]
        if not lines:
            return "No adapter releases published yet — sleep will report them once CI trains one."
        return ("Latest GitHub releases (pull manually into memory/checkpoints/ when ready): "
                + " | ".join(lines[:3]))
    except Exception:
        return None


# ------------------------------------------------------------- orchestrator
def run_sleep(*, trigger: str = "user_requested") -> SleepReport:
    init_db()
    settings = get_settings()
    backup_path = backup_db("pre-sleep")
    started = now_iso()
    t0 = time.time()
    report = SleepReport(id=new_id("sleep"), started_at=started, finished_at=started, trigger=trigger)
    try:
        with connect() as con:
            last_sleep = get_meta(con, "last_sleep_at")
            # Stage 1
            replay = stage_replay(con, last_sleep=last_sleep)
            report.episodes_reviewed = len(replay)
            # Stage 2
            cons = stage_consolidate(con, replay)
            report.lessons_consolidated = cons["lessons"]
            report.concepts_linked = cons["linked"]
            report.duplicates_merged = cons["merged"]
            # Stage 3
            patterns = stage_patterns(con, last_sleep=last_sleep)
            for p in patterns:
                report.notes.append(p)
            # Stage 4
            org = stage_organize(con)
            report.conflicts_flagged = org["conflicts"]
            if org["concepts_merged"]:
                report.notes.append(f"Merged {org['concepts_merged']} duplicate concept nodes.")
            for c in org["conflict_detail"]:
                report.unresolved.append(f"Conflict: {c['src']} ⇄ {c['dst']}")
            # Stage 5
            forget = stage_forget(con, half_life_days=settings.decay_half_life_days,
                                  archive_threshold=settings.archive_threshold)
            report.episodes_archived = forget["archived"]
            if forget["archive_file"]:
                report.notes.append(f"Archived (recoverable) low-priority memories → {forget['archive_file']}")
            # Stage 6
            comp = stage_compile(con, last_sleep=last_sleep, patterns=patterns)
            report.skills_reverified = comp["reverified"]
            report.weakness_domains = comp["weakness_domains"]
            skills = comp["skills"]
            shard_summary = comp["shard"]
            if shard_summary:
                report.skills_compiled = len(skills)
                report.shard_path = shard_summary["shard_path"]
                report.shard_examples = shard_summary["examples"]
                report.shard_sha256 = shard_summary["sha256"]
            # Stage 7
            dispatch = stage_dispatch(con, shard_summary=shard_summary, report=report, trigger=trigger)
            report.github_dispatch = dispatch["dispatch"]
            report.notes.extend(dispatch["notes"])
            set_meta(con, "last_sleep_at", now_iso())
            # persist report
            con.execute("INSERT INTO sleep_runs(id, started_at, finished_at, trigger, report_json) VALUES (?,?,?,?,?)",
                        (report.id, report.started_at, now_iso(), trigger, report.model_dump_json()))
    except BaseException as e:
        report.finished_at = now_iso()
        report.unresolved.append(f"SLEEP INTERRUPTED: {type(e).__name__}: {e}")
        report.notes.append(f"Pre-sleep backup kept at: {backup_path}")
        _write_sleep_logs(report)
        raise
    report.finished_at = now_iso()
    elapsed = time.time() - t0
    report.notes.append(f"Sleep completed in {elapsed:.2f}s. Backup: {backup_path}")
    _write_sleep_logs(report)
    return report


def _write_sleep_logs(report: SleepReport) -> None:
    settings = get_settings()
    settings.sleep_logs.mkdir(parents=True, exist_ok=True)
    ts = utcnow_compact()
    (settings.sleep_logs / f"sleep_{ts}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md = [
        f"# MiniCoder Sleep Report — {report.id}",
        f"*Trigger:* {report.trigger} · *Window:* {report.started_at} → {report.finished_at}",
        "",
        f"- Episodes replayed: **{report.episodes_reviewed}**",
        f"- Lessons consolidated: **{report.lessons_consolidated}** · Concepts linked: **{report.concepts_linked}** · Duplicates merged: **{report.duplicates_merged}**",
        f"- Conflicts flagged: **{report.conflicts_flagged}** · Episodes archived: **{report.episodes_archived}**",
        f"- Skills compiled: **{report.skills_compiled}** ({report.shard_examples} examples) · Re-verified: **{report.skills_reverified}**",
        f"- Shard: `{report.shard_path}` · sha256 `{(report.shard_sha256 or '')[:16]}…`",
        f"- GitHub dispatch: **{report.github_dispatch}**",
        "",
        "## Notes", *[f"- {n}" for n in report.notes],
        "",
        "## Unresolved / flagged", *([f"- {u}" for u in report.unresolved] or ["- none"]),
    ]
    (settings.sleep_logs / f"sleep_{ts}.md").write_text("\n".join(md), encoding="utf-8")


def latest_sleep_report() -> dict | None:
    with connect() as con:
        row = con.execute("SELECT report_json FROM sleep_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    return json.loads(row["report_json"]) if row else None
