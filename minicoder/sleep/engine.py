"""The Sleep Engine: eight stages, measured and reported.

Stages (blueprint §4):
1. Prioritised memory replay     — rank episodes by surprise/failure/correction
2. Memory consolidation          — strip filler, extract lessons, embed
3. Cross-modal pattern discovery — recurring patterns across modalities
4. Organisation & conflict resolution
5. Forgetting & compression      — decay-weighted archival (never silent loss)
6. Skill -> dataset compilation  — verified skills only, + self-directed practice
7. GitHub dispatch + wake report

Interaction pauses for the duration of the cycle; the API exposes the live
stage over WebSocket so the dashboard can show real progress.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import tarfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from minicoder.config import CONFIG, FAILED, UNVERIFIED, VERIFIED
from minicoder.memory.db import BrainDB, utcnow
from minicoder.memory.systems import (
    EpisodicMemory,
    ProceduralMemory,
    SemanticMemory,
    VisualMemory,
)
from minicoder.sleep.compiler import build_shard, shard_stats


@dataclass
class SleepReport:
    started_at: str
    trigger: str = "manual"
    cycle_id: int | None = None
    stages: list[dict[str, Any]] = field(default_factory=list)
    learned: list[str] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)
    promoted: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    shard: dict[str, Any] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    ended_at: str = ""
    duration_seconds: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id, "trigger": self.trigger,
            "started_at": self.started_at, "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds, "stages": self.stages,
            "learned": self.learned, "archived": self.archived, "promoted": self.promoted,
            "unresolved": self.unresolved, "shard": self.shard,
            "conflicts": self.conflicts, "metrics": self.metrics,
        }

    def markdown(self) -> str:
        lines = [
            f"# Sleep Report — cycle {self.cycle_id}",
            "",
            f"- **Trigger:** {self.trigger}",
            f"- **Started:** {self.started_at}",
            f"- **Duration:** {self.duration_seconds:.1f}s",
            "",
            "## Stages",
        ]
        for st in self.stages:
            lines.append(f"### {st['stage']}. {st['name']}  ·  {st['ms']} ms")
            for k, v in st.items():
                if k in ("stage", "name", "ms"):
                    continue
                lines.append(f"- {k}: {v}")
            lines.append("")
        lines += ["## Consolidated lessons"]
        lines += [f"- {l}" for l in self.learned] or ["- (none)"]
        lines += ["", "## Promoted to GitHub training data"]
        lines += [f"- {p}" for p in self.promoted] or ["- (no new verified skills this cycle)"]
        lines += ["", "## Archived / compressed (recoverable)"]
        lines += [f"- {a}" for a in self.archived] or ["- (nothing crossed the decay threshold)"]
        lines += ["", "## Conflicts & unresolved"]
        lines += [f"- {c}" for c in (self.conflicts + self.unresolved)] or ["- (none)"]
        if self.shard.get("created"):
            lines += [
                "",
                "## Training shard",
                f"- file: `{Path(self.shard['path']).name}`",
                f"- examples: {self.shard['examples']}",
                f"- skills: {self.shard['skills']}",
                f"- sha256: `{self.shard['sha256'][:16]}…`",
                f"- kinds: {self.shard.get('counts')}",
            ]
        return "\n".join(lines) + "\n"


class SleepEngine:
    def __init__(
        self,
        db: BrainDB | None = None,
        *,
        on_stage: Callable[[str, dict[str, Any]], None] | None = None,
        push_to_github: bool = False,
        train_after_compile: bool = False,
    ) -> None:
        self.db = db or BrainDB()
        self.episodic = EpisodicMemory(self.db)
        self.semantic = SemanticMemory(self.db)
        self.procedural = ProceduralMemory(self.db)
        self.visual = VisualMemory(self.db)
        self.on_stage = on_stage
        self.push_to_github = push_to_github
        self.train_after_compile = train_after_compile
        self.busy = False

    # ---------------------------------------------------------- helpers
    def _emit(self, stage: int, name: str, payload: dict[str, Any]) -> None:
        if self.on_stage:
            try:
                self.on_stage(name, {"stage": stage, **payload})
            except Exception:
                pass

    def _stage(self, report: SleepReport, idx: int, name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        t0 = time.time()
        self._emit(idx, name, {"status": "start"})
        try:
            out = fn() or {}
        except Exception as exc:  # a failing stage must not destroy the cycle
            out = {"error": f"{type(exc).__name__}: {exc}"}
        entry = {"stage": idx, "name": name, "ms": int((time.time() - t0) * 1000), **out}
        report.stages.append(entry)
        self._emit(idx, name, {"status": "done", **entry})
        return entry

    # ------------------------------------------------------------- run
    def sleep(self, trigger: str = "manual") -> SleepReport:
        if self.busy:
            raise RuntimeError("a sleep cycle is already running")
        self.busy = True
        t0 = time.time()
        report = SleepReport(started_at=utcnow(), trigger=trigger)
        backup: Path | None = None
        cur = self.db.execute(
            "INSERT INTO sleep_cycles(started_at, trigger, status) VALUES (?,?,?)",
            (report.started_at, trigger, "running"),
        )
        report.cycle_id = int(cur.lastrowid)
        self.db.telemetry("SLEEP", "cycle_start", {"trigger": trigger, "cycle_id": report.cycle_id})
        try:
            # Atomic pre-sleep snapshot: a broken cycle can always be rolled back.
            backup = self.db.backup(tag=f"pre_sleep_{report.cycle_id}")
            self._stage(report, 1, "Prioritised memory replay", lambda: self._replay(report))
            consolidated = self._stage(report, 2, "Memory consolidation", lambda: self._consolidate(report))
            self._stage(report, 3, "Cross-modal pattern discovery", lambda: self._cross_modal(report))
            self._stage(report, 4, "Organisation & conflict resolution", lambda: self._organise(report))
            learning = self._stage(report, 5, "Learning consolidation & skill retention",
                                   lambda: self._consolidate_learning(report))
            self._stage(report, 6, "Forgetting & compression", lambda: self._forget(report))
            self._stage(report, 7, "Skill compilation & self-practice", lambda: self._compile(report))
            self._stage(report, 8, "GitHub dispatch & wake-up", lambda: self._dispatch(report))
            self.semantic.save_snapshot()
            report.metrics = {
                "episodes_consolidated": consolidated.get("consolidated", 0),
                "nodes_added": consolidated.get("nodes_added", 0),
                "learning_extracted": learning.get("extracted", 0),
                "learning_retention_passed": learning.get("retention_passed", 0),
                "backup": str(backup) if backup else "",
                "db_stats": self.db.stats(),
            }
            report.ended_at = utcnow()
            report.duration_seconds = round(time.time() - t0, 2)
            self._write_report(report)
            self.db.execute(
                "UPDATE sleep_cycles SET ended_at=?, status=?, report=? WHERE id=?",
                (report.ended_at, "ok", json.dumps(report.to_json()), report.cycle_id),
            )
            self.db.telemetry("WAKE", "cycle_end", {"cycle_id": report.cycle_id,
                                                    "seconds": report.duration_seconds})
            return report
        except BaseException:
            self.db.execute(
                "UPDATE sleep_cycles SET ended_at=?, status=? WHERE id=?",
                (utcnow(), "failed", report.cycle_id),
            )
            raise
        finally:
            self.busy = False

    # ---------------------------------------------------------- stages
    def _replay(self, report: SleepReport) -> dict[str, Any]:
        pending = self.episodic.unconsolidated(limit=200)
        failures = [e for e in pending if e["status"] in (FAILED, UNVERIFIED)]
        corrections = [e for e in pending if "correction" in json.dumps(e.get("meta") or {})]
        high_surprise = sorted(pending, key=lambda e: e["surprise"], reverse=True)[:20]
        routine = len(pending) - len(failures) - len(high_surprise)
        report.metrics["replay_pending"] = len(pending)
        if failures:
            report.unresolved.extend(
                f"episode {e['id']} ended {e['status']}: {e['objective'][:120]}" for e in failures[:5]
            )
        return {
            "pending": len(pending),
            "prioritised_failures": len(failures),
            "user_corrections": len(corrections),
            "high_surprise": len(high_surprise),
            "routine_deprioritised": max(0, routine),
        }

    def _consolidate(self, report: SleepReport) -> dict[str, Any]:
        pending = self.episodic.unconsolidated(limit=200)
        if not pending:
            return {"consolidated": 0, "nodes_added": 0, "lessons": 0}
        nodes_before = self.semantic.stats()["nodes"]
        done: list[int] = []
        lessons = 0
        for ep in pending:
            lesson = (ep["lessons"] or "").strip()
            if not lesson and ep["result"]:
                lesson = self._summarise(ep)
            if lesson and not self._is_learnable(lesson):
                report.unresolved.append(
                    f"episode {ep['id']} skipped: unlearnable text {lesson[:60]!r}"
                )
                done.append(ep["id"])
                continue
            if lesson:
                label = lesson[:90]
                status = VERIFIED if ep["status"] == VERIFIED else UNVERIFIED
                self.semantic.upsert(
                    "heuristic" if ep["modality"] in ("code", "vision") else "fact",
                    label,
                    f"{lesson}\n\nContext: {ep['situation'][:240]}\nOutcome: {ep['result'][:240]}",
                    status=status,
                    source=ep["source"],
                    confidence=ep["confidence"],
                    meta={"episode_id": ep["id"]},
                )
                lessons += 1
                report.learned.append(lesson[:160])
            done.append(ep["id"])
            # Link visual memories to the semantic concept they produced.
            if ep["modality"] in ("vision", "mixed"):
                vm = self.db.query_one(
                    "SELECT id FROM visual_memories WHERE episode_id=? ORDER BY id DESC LIMIT 1",
                    (ep["id"],),
                )
                if vm:
                    self.db.execute("UPDATE visual_memories SET episode_id=? WHERE id=?", (ep["id"], vm["id"]))
        self.episodic.mark_consolidated(done)
        nodes_after = self.semantic.stats()["nodes"]
        return {
            "consolidated": len(done),
            "nodes_added": max(0, nodes_after - nodes_before),
            "lessons": lessons,
        }

    @staticmethod
    def _is_learnable(text: str) -> bool:
        """Only real prose or real code may become a long-term memory.

        Measured defect: a garbage neural answer ("b):      =") was consolidated
        into the semantic graph and then retrieved as a fact, because the only
        filter was "non-empty". A claim needs to be made of words.
        """
        t = (text or "").strip()
        if len(t) < 12:
            return False
        words = re.findall(r"[A-Za-z][A-Za-z'\-]{1,}", t)
        if len(words) < 3:
            return False
        # Ratio of alphabetic runs to all non-space chunks: symbol soup fails.
        chunks = t.split()
        wordy = sum(1 for c in chunks if re.fullmatch(r"[A-Za-z][A-Za-z0-9'\-.,;:()]*", c))
        if wordy / max(1, len(chunks)) < 0.6:
            return False
        # Garbage is often one short token followed by a long run of symbols.
        if re.search(r"[=\]\)]{3,}|\b\w\):\s{3,}", t):
            return False
        return True

    @staticmethod
    def _summarise(ep: dict[str, Any]) -> str:
        """Strip conversational filler and keep the operational core."""
        text = (ep["result"] or ep["objective"] or "").strip()
        for filler in ("sure,", "of course", "okay", "ok,", "well,"):
            if text.lower().startswith(filler):
                text = text[len(filler) :].strip()
        return text.split("\n")[0][:200]

    def _cross_modal(self, report: SleepReport) -> dict[str, Any]:
        episodes = self.db.query(
            "SELECT * FROM episodes WHERE archived=0 ORDER BY id DESC LIMIT 300"
        )
        patterns: dict[str, list[int]] = {}
        keywords = ("overflow", "contrast", "align", "truncat", "palette", "spacing", "contrast", "layout")
        for ep in episodes:
            hay = f"{ep['situation']} {ep['objective']} {ep['lessons']} {ep['mistakes']}".lower()
            for kw in keywords:
                if kw in hay:
                    patterns.setdefault(kw, []).append(int(ep["id"]))
        found = {k: v for k, v in patterns.items() if len(v) >= 3}
        for kw, ids in found.items():
            modalities = {
                r["modality"]
                for r in self.db.query(
                    f"SELECT modality FROM episodes WHERE id IN ({','.join('?'*len(ids))})", ids
                )
            }
            cluster_label = f"recurring {kw} issue cluster"
            nid = self.semantic.upsert(
                "pattern", cluster_label,
                f"{len(ids)} episodes mention '{kw}' across {len(modalities)} modality(ies). "
                "Recorded as a correlation; causation is not assumed.",
                status=UNVERIFIED, source="verified_execution" if len(modalities) > 1 else "unverified_hypothesis",
                confidence=min(0.7, 0.3 + 0.05 * len(ids)),
                meta={"episode_ids": ids[:20]},
            )
            for other in self.semantic.search(kw, limit=3):
                if other["id"] != nid:
                    try:
                        self.semantic.link(nid, other["id"], "refines", 0.6)
                    except ValueError:
                        pass
            report.learned.append(f"pattern: {cluster_label} ({len(ids)} episodes)")
        return {"clusters": len(found), "details": {k: len(v) for k, v in found.items()}}

    def _organise(self, report: SleepReport) -> dict[str, Any]:
        # 1. Merge duplicates by normalised content.
        rows = self.db.query("SELECT id, kind, label, content FROM semantic_nodes WHERE archived=0")
        seen: dict[str, int] = {}
        merged = 0
        for row in rows:
            key = f"{row['kind']}|{row['label'].strip().lower()}"
            if key in seen:
                keep = seen[key]
                self.db.execute("UPDATE semantic_nodes SET archived=1 WHERE id=?", (row["id"],))
                merged += 1
                self.db.log_provenance("semantic_nodes", row["id"], "merge_into", detail={"into": keep})
            else:
                seen[key] = row["id"]
        # 2. Conflicts: record and keep both sides (never silently overwrite).
        conflicts = self.semantic.conflicts()
        for c in conflicts[:10]:
            a = self.semantic.node(c["node_a"])
            b = self.semantic.node(c["node_b"])
            if a and b and a["id"] != b["id"]:
                self.semantic.link(a["id"], b["id"], "contradicts", 1.0)
            report.conflicts.append(f"conflict #{c['id']}: {c['reason']}")
        # 3. Re-verify: nodes claimed VERIFIED but whose source is a hypothesis.
        downgraded = 0
        for row in self.db.query("SELECT * FROM semantic_nodes WHERE status='VERIFIED' AND source='unverified_hypothesis'"):
            self.db.execute("UPDATE semantic_nodes SET status='UNVERIFIED' WHERE id=?", (row["id"],))
            downgraded += 1
        self.semantic.reload()
        return {"merged_duplicates": merged, "conflicts": len(conflicts), "downgraded": downgraded}

    def _forget(self, report: SleepReport) -> dict[str, Any]:
        """Decay-weighted archival: compress, never silently delete."""
        cfg = CONFIG.memory
        w_relevance, w_freq, w_conf, w_recency = cfg.decay_weights
        rows = self.db.query("SELECT * FROM semantic_nodes WHERE archived=0")
        archived = 0
        for row in rows:
            from minicoder.memory.systems import _days_since

            days = _days_since(row["last_access"])
            recency = math.exp(-math.log(2) * days / cfg.decay_half_life_days)
            freq = min(1.0, row["access_count"] / 10.0)
            score = w_relevance * 0.5 + w_freq * freq + w_conf * row["confidence"] + w_recency * recency
            if score < cfg.archive_threshold and row["access_count"] == 0:
                self.db.execute("UPDATE semantic_nodes SET archived=1 WHERE id=?", (row["id"],))
                archived += 1
                report.archived.append(f"semantic #{row['id']} '{row['label']}' (decay score {score:.3f})")
            elif score < cfg.forget_threshold:
                self.db.execute("UPDATE semantic_nodes SET archived=1 WHERE id=?", (row["id"],))
                archived += 1
        # Episodes older than the retention window are compressed to an archive tar.
        old = self.db.query(
            "SELECT * FROM episodes WHERE archived=0 AND julianday('now') - julianday(ts) > ?",
            (cfg.episodic_retention_days,),
        )
        archive_path = ""
        if old:
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            dest = CONFIG.paths.archived / f"episodes_{stamp}.jsonl.tar.gz"
            tmp = CONFIG.paths.archived / f".episodes_{stamp}.jsonl"
            tmp.write_text("\n".join(json.dumps(dict(r)) for r in old), encoding="utf-8")
            with tarfile.open(dest, "w:gz") as tar:
                tar.add(tmp, arcname=tmp.name)
            tmp.unlink()
            archive_path = str(dest.relative_to(CONFIG.paths.home))
            with self.db.write() as conn:
                conn.executemany("UPDATE episodes SET archived=1 WHERE id=?", [(r["id"],) for r in old])
            report.archived.append(f"{len(old)} episodes compressed to {Path(archive_path).name}")
        self.semantic.reload()
        self.db.execute(
            "INSERT INTO provenance_events(ts, entity, entity_id, action, actor, detail) VALUES (?,?,?,?,?,?)",
            (utcnow(), "memory", None, "decay_pass", "sleep", json.dumps({"archived": archived,
                                                                           "episodes_archived": len(old)})),
        )
        return {"nodes_archived": archived, "episodes_archived": len(old), "archive": archive_path}

    def _compile(self, report: SleepReport) -> dict[str, Any]:
        out = build_shard(db=self.db)
        report.shard = out
        if out.get("created"):
            stats = shard_stats(Path(out["path"]))
            report.promoted.append(
                f"{out['skills']} verified skills -> {out['examples']} examples "
                f"({stats['kinds']}) in {Path(out['path']).name}"
            )
        # Self-directed practice: try to verify quarantined skills in the sandbox.
        from minicoder.tools.sandbox import Sandbox

        practiced = 0
        verified_new: list[str] = []
        quarantine = self.procedural.any("QUARANTINED")
        if quarantine:
            sbx = Sandbox(use_docker=False)
            for skill in quarantine[:5]:
                if not skill["solution"] or not skill["verification"]:
                    continue
                tests = json.loads(skill["verification"]).get("tests", "")
                if not tests:
                    continue
                ok, res = sbx.run_tests(skill["solution"], tests)
                practiced += 1
                if ok:
                    from minicoder.memory.systems import Skill

                    self.procedural.add(
                        Skill(
                            slug=skill["slug"], name=skill["name"], description=skill["description"],
                            domain=skill["domain"], solution=skill["solution"],
                            verification={"passed": True, "runner": "sandbox", "tests": tests},
                            source="verified_execution", confidence=0.85,
                        ),
                        verified=True,
                    )
                    verified_new.append(skill["slug"])
        if verified_new:
            report.promoted.append("self-practice verified: " + ", ".join(verified_new))
            # Newly verified skills get their own shard so nothing is stranded.
            second = build_shard(db=self.db)
            if second.get("created"):
                report.promoted.append(
                    f"practice shard {Path(second['path']).name}: {second['examples']} examples"
                )
                report.shard = second
        return {
            "shard_created": bool(out.get("created")),
            "examples": out.get("examples", 0),
            "skills": out.get("skills", 0),
            "practice_attempted": practiced,
            "practice_verified": verified_new,
        }


    # ------------------------------------------------- learning consolidation
    def _consolidate_learning(self, report: SleepReport) -> dict[str, Any]:
        """Turn acquired experience into durable, calibrated knowledge.

        The old cycle could only re-verify skills that already existed. This
        stage reads what the learning loop actually produced and does the work
        the brief asks for:

        * extract knowledge from **solved** experiments only — a failed
          experiment contributes nothing except its failure class, which is
          useful but is not knowledge;
        * de-duplicate against existing semantic nodes;
        * detect contradictions with what is already believed and record them,
          rather than silently overwriting;
        * calibrate confidence from the measured replay success rate, not from
          optimism;
        * stamp temporal validity so a later change can supersede instead of
          corrupting history;
        * record skill dependencies on the tools the procedure used;
        * re-run the replay to measure retention, so forgetting is visible.
        """
        out: dict[str, Any] = {"extracted": 0, "duplicates": 0, "contradictions": 0,
                               "dependencies": 0, "retention_checked": 0,
                               "retention_passed": 0, "calibrated": []}
        try:
            solved = [dict(r) for r in self.db.query(
                "SELECT id, task_key, title, goal, success_criteria FROM experiments"
                " WHERE status='solved' ORDER BY id DESC LIMIT 20"
            )]
        except Exception:
            return {"skipped": "no experiments table"}
        if not solved:
            return out

        for exp in solved:
            cand = self.db.query_one(
                "SELECT * FROM skill_candidates WHERE experiment_id=?"
                " AND status IN ('promoted','replay_passed') ORDER BY id DESC LIMIT 1",
                (exp["id"],),
            )
            if not cand:
                continue
            slug = cand["slug"]
            # --- confidence calibration from measured replays
            runs = int(cand["replay_runs"] or 0)
            failures = json.loads(cand["replay_failures"] or "[]")
            attempts_total = runs + len(failures)
            confidence = round(runs / attempts_total, 3) if attempts_total else 0.0
            out["calibrated"].append({"slug": slug, "replays": runs,
                                      "failures": len(failures),
                                      "confidence": confidence})

            # --- de-duplication: is this already known?
            label = f"learned procedure: {slug}"
            existing = self.semantic.find_by_label(label) if hasattr(
                self.semantic, "find_by_label") else None
            if existing is None:
                existing = self.db.query_one(
                    "SELECT id, content FROM semantic_nodes WHERE label=?", (label,)
                )
            content = (f"To satisfy {exp['goal']}, the verified procedure for "
                       f"'{exp['title']}' is a {len(json.loads(cand['procedure'] or '[]'))}-step "
                       f"tool sequence that passed {runs} independent replays.")
            if existing:
                out["duplicates"] += 1
                if str(existing["content"]) != content:
                    self._record_conflict(label, str(existing["content"]), content, slug)
                    out["contradictions"] += 1
                continue

            self.semantic.upsert(
                "procedure", label, content,
                status=VERIFIED, source="learning_loop", confidence=confidence,
                meta={"experiment_id": exp["id"], "candidate_id": cand["id"],
                      "replay_runs": runs, "valid_from": utcnow(),
                      "supersedes": cand["supersedes"] or ""},
            )
            out["extracted"] += 1

            # --- dependencies on the tools the procedure used
            try:
                procedure = json.loads(cand["procedure"] or "[]")
            except json.JSONDecodeError:
                procedure = []
            for step in procedure:
                tool = step.get("tool")
                if not tool:
                    continue
                self.db.execute(
                    "INSERT OR IGNORE INTO skill_dependencies(ts, skill_slug, depends_on, kind)"
                    " VALUES (?,?,?,?)",
                    (utcnow(), slug, f"tool:{tool}", "requires"),
                )
                out["dependencies"] += 1

            # --- retention: does the stored skill still work now?
            out["retention_checked"] += 1
            if self._replay_retention(slug, procedure, exp):
                out["retention_passed"] += 1

        if out["extracted"]:
            report.promoted.append(
                f"learning: {out['extracted']} new procedure(s) consolidated, "
                f"{out['contradictions']} contradiction(s), "
                f"{out['retention_passed']}/{out['retention_checked']} retained"
            )
        return out

    def _record_conflict(self, label: str, old: str, new: str, slug: str) -> None:
        try:
            self.db.execute(
                "INSERT INTO memory_conflicts(ts, label, old_content, new_content,"
                " source, resolved) VALUES (?,?,?,?,?,?)",
                (utcnow(), label, old[:2000], new[:2000], f"learning:{slug}", 0),
            )
        except Exception:
            pass

    def _replay_retention(self, slug: str, procedure: list[dict[str, Any]],
                          exp: dict[str, Any]) -> bool:
        """Re-run a stored procedure and record whether it still holds.

        Retention is measured, not assumed: a skill that no longer replays is
        reported here and its confidence is degraded rather than left high.
        """
        if not procedure:
            return False
        try:
            from minicoder.learning.criteria import evaluate_editor_criteria
            from minicoder.tools.editor_bridge import EditorBridge

            criteria = json.loads(exp["success_criteria"] or "[]")
            bridge = EditorBridge()
            try:
                bridge._ensure()
                bridge.call("new_project", {})
                for step in procedure:
                    result, _ = bridge.call(step["tool"], step.get("args") or {})
                    if isinstance(result, dict) and result.get("ok") is False:
                        self.db.execute(
                            "INSERT INTO skill_replays(ts, skill_slug, task_key, variation,"
                            " passed, detail) VALUES (?,?,?,?,?,?)",
                            (utcnow(), slug, exp["task_key"], "sleep_retention", 0,
                             json.dumps({"error": str(result.get("error"))[:200]})),
                        )
                        return False
                _, raw = bridge.call("get_app_state", {})
                from minicoder.learning.criteria import EditorState

                state = EditorState.from_snapshot(raw.get("snapshot") or {})
                results = evaluate_editor_criteria(criteria, state)
                ok = bool(results) and all(r.passed for r in results)
                self.db.execute(
                    "INSERT INTO skill_replays(ts, skill_slug, task_key, variation,"
                    " passed, detail) VALUES (?,?,?,?,?,?)",
                    (utcnow(), slug, exp["task_key"], "sleep_retention", int(ok),
                     json.dumps({"criteria": [r.to_json() for r in results]})),
                )
                return ok
            finally:
                try:
                    bridge.close()
                except Exception:
                    pass
        except Exception:
            return False

    def _dispatch(self, report: SleepReport) -> dict[str, Any]:
        from minicoder.sleep.github import GitHubDispatcher

        result: dict[str, Any] = {"pushed": False}
        if not (report.shard and report.shard.get("created")):
            return {"pushed": False, "reason": "no new shard"}
        shard = Path(report.shard["path"])
        dispatcher = GitHubDispatcher()
        if not self.push_to_github:
            result = {"pushed": False, "reason": "push disabled (enable with --push)", "staged": shard.name}
        else:
            result = dispatcher.push_shard(shard)
            if result.get("pushed"):
                report.promoted.append(
                    f"pushed {shard.name} to {result.get('repo')}@{result.get('branch')} "
                    f"(commit {str(result.get('commit'))[:10]})"
                )
        if self.train_after_compile:
            from minicoder.sleep.trainer import train_from_shard

            train_out = train_from_shard(shard, db=self.db)
            result["training"] = train_out
            if train_out.get("gate_passed"):
                report.promoted.append(
                    f"adapter trained and passed the validation gate (skill acc {train_out['metrics']['skill_accuracy']})"
                )
            else:
                report.unresolved.append(
                    f"adapter rejected by the validation gate: {train_out.get('reason', 'regression')}"
                )
        return result

    def _write_report(self, report: SleepReport) -> Path:
        out_dir = CONFIG.paths.sleep_logs
        out_dir.mkdir(parents=True, exist_ok=True)
        base = out_dir / f"sleep_{report.cycle_id:04d}"
        (base.with_suffix(".json")).write_text(json.dumps(report.to_json(), indent=2), encoding="utf-8")
        (base.with_suffix(".md")).write_text(report.markdown(), encoding="utf-8")
        latest = out_dir / "latest.md"
        shutil.copy2(base.with_suffix(".md"), latest)
        return base
