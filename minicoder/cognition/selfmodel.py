"""Self-knowledge: answers about the system's own state, from its own records.

Measured gap: "Summarise your last sleep cycle" was refused even though the report was on
disk, and "How many skills do you have" had no path at all. A system that keeps provenance
but cannot read it back is not trustworthy about itself.

Everything here is read from the database or a recorded report. Nothing is generated,
estimated or padded: if a report is missing the answer says so.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Questions that are about the system rather than about the world or the canvas.
_SELF_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(sleep|slept|nightly|consolidat\w*)\b", "sleep"),
    (r"\b(how many|list|show|tell me about)\b.*\b(skills?|procedures?)\b", "skills"),
    (r"\bwhat (have|did) you (learn|acquired?)\b", "learned"),
    (r"\b(research|phase 3|benchmark|acquisition rate|how well do you)\b", "research"),
    (r"\b(how much|what) do you (remember|know|hold)\b|\bmemor(y|ies) (size|stats)\b", "memory"),
    (r"\b(your|you) (earlier|previously)\b.*\b(verify|verif\w+)\b", "verification"),
)


def classify_self(question: str) -> str | None:
    text = question.lower().strip()
    if not text:
        return None
    for pattern, topic in _SELF_PATTERNS:
        if re.search(pattern, text):
            # "how do I consolidate a design" is about the canvas, not about us.
            if topic == "sleep" and re.search(r"\bhow (do|can) i\b", text):
                return None
            return topic
    return None


def _load_report(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _latest_sleep(home: Path) -> dict[str, Any] | None:
    logs = home / "memory" / "sleep_logs"
    if not logs.exists():
        return None
    files = sorted(logs.glob("sleep_*.json"))
    return _load_report(files[-1]) if files else None


def _sleep_answer(home: Path) -> str:
    report = _latest_sleep(home)
    if not report:
        return "I have no sleep report on disk yet — run a cycle and I can summarise it."
    stages = report.get("stages", [])
    failed = [s for s in stages if s.get("error")]
    bits = [
        f"Last sleep cycle was #{report.get('cycle_id')} "
        f"({(report.get('trigger') or 'manual')} trigger) and took "
        f"{report.get('duration_seconds', 0):.1f}s across {len(stages)} stages."
    ]
    for stage in stages:
        name = str(stage.get("name", "")).lower()
        if stage.get("error"):
            bits.append(f"Stage {stage['stage']} ({stage.get('name')}) failed: {stage['error'][:120]}.")
        elif stage.get("stage") == 2:
            bits.append(f"Consolidation merged {stage.get('consolidated', 0)} episodes into "
                        f"{stage.get('nodes_added', 0)} new node(s).")
        elif stage.get("stage") == 5 and "retention" in name:
            bits.append(f"Skill retention replayed {stage.get('retention_checked', 0)} "
                        f"procedure(s): {stage.get('retention_passed', 0)} passed.")
        elif stage.get("stage") == 7 and stage.get("shard_created"):
            bits.append(f"Compilation produced a shard with {stage.get('examples', 0)} "
                        f"examples from {stage.get('skills', 0)} skill(s).")
    if failed:
        bits.append(f"{len(failed)} stage(s) reported an error; the report is at "
                    f"memory/sleep_logs/.")
    else:
        bits.append("Every stage completed without an error.")
    return " ".join(bits)


def _skills_answer(db: Any) -> str:
    total = db.query_one("SELECT COUNT(*) FROM skills")[0]
    verified = db.query_one("SELECT COUNT(*) FROM skills WHERE status='VERIFIED'")[0]
    rows = db.query(
        "SELECT s.slug, COUNT(r.id) AS runs, COALESCE(SUM(r.passed), 0) AS passed "
        "FROM skills s LEFT JOIN skill_replays r ON r.skill_slug = s.slug "
        "GROUP BY s.slug HAVING runs > 0 ORDER BY runs DESC LIMIT 4"
    )
    learned = db.query_one("SELECT COUNT(*) FROM skills WHERE slug LIKE 'learned_%'")[0]
    bits = [f"I hold {total} skills ({verified} verified, {learned} learned by the acquisition loop)."]
    if rows:
        examples = ", ".join(f"{r['slug']} {int(r['passed'])}/{int(r['runs'])}" for r in rows)
        bits.append(f"Replay evidence: {examples}.")
    else:
        bits.append("No skill has replay evidence yet.")
    return " ".join(bits)


def _learned_answer(db: Any, home: Path) -> str:
    row = db.query_one(
        "SELECT slug, description FROM skills WHERE slug LIKE 'learned_%' ORDER BY id DESC LIMIT 1"
    )
    if not row:
        return "I have not promoted a skill from the acquisition loop yet."
    replays = db.query_one(
        "SELECT COUNT(*) AS runs, COALESCE(SUM(passed), 0) AS passed "
        "FROM skill_replays WHERE skill_slug=?", (row["slug"],)
    )
    bits = [f"The most recent procedure I learned is {row['slug']}: {str(row['description'])[:200]}."]
    if replays and replays["runs"]:
        bits.append(f"It has been replayed {int(replays['runs'])} time(s), "
                    f"passing {int(replays['passed'])}.")
    return " ".join(bits)


def _research_answer(home: Path) -> str:
    base = home / "datasets" / "research"
    acquisition = _load_report(base / "acquisition_latest.json")
    if not acquisition:
        return ("I have no Phase 3 research report on disk, so I will not quote a number "
                "I cannot show.")
    rates = acquisition.get("rates", {})
    retention = _load_report(base / "retention_latest.json") or {}
    bits = [
        f"In the last blind experiment ({acquisition.get('experiment_id')}, "
        f"seeds {acquisition.get('config', {}).get('seeds')}) my baseline scored "
        f"{rates.get('A', 0):.3f} on hidden tests and the full system scored "
        f"{rates.get('E', 0):.3f}."
    ]
    if retention:
        bits.append(f"{retention.get('verified_retained', 0)} of "
                    f"{retention.get('verified_at_acquisition', 0)} verified procedures "
                    f"still pass on re-check.")
    bits.append("Those numbers come from datasets/research/ and are reproducible with "
                "`minicoder research reproduce`.")
    return " ".join(bits)


def _memory_answer(db: Any) -> str:
    episodes = db.query_one("SELECT COUNT(*) FROM episodes")[0]
    nodes = db.query_one("SELECT COUNT(*) FROM semantic_nodes")[0]
    edges = db.query_one("SELECT COUNT(*) FROM semantic_edges")[0]
    conflicts = db.query_one("SELECT COUNT(*) FROM memory_conflicts")[0]
    return (f"I hold {episodes} episodes, {nodes} semantic nodes with {edges} typed edges, "
            f"and {conflicts} recorded conflicts between memories.")


def _verification_answer(db: Any) -> str:
    rows = db.query(
        "SELECT status, COUNT(*) AS n FROM skills GROUP BY status ORDER BY n DESC"
    )
    parts = ", ".join(f"{r['n']} {r['status'].lower()}" for r in rows) or "none"
    return (f"Skills by verification state: {parts}. Only VERIFIED procedures are offered as "
            f"procedures; unverified ones stay hypotheses.")


def self_answer(question: str, *, db: Any = None, home: Path | None = None) -> dict[str, Any] | None:
    """Return {"text", "topic"} for a self-directed question, else None."""
    topic = classify_self(question)
    if topic is None:
        return None
    if db is None or home is None:
        from minicoder.config import CONFIG
        from minicoder.memory.db import BrainDB

        db = db or BrainDB()
        home = home or CONFIG.paths.home
    try:
        if topic == "sleep":
            text = _sleep_answer(home)
        elif topic == "skills":
            text = _skills_answer(db)
        elif topic == "learned":
            text = _learned_answer(db, home)
        elif topic == "research":
            text = _research_answer(home)
        elif topic == "memory":
            text = _memory_answer(db)
        else:
            text = _verification_answer(db)
    except Exception as exc:  # noqa: BLE001 - a broken self-report must not break chat
        return {"text": f"I could not read my own records ({type(exc).__name__}).",
                "topic": topic}
    return {"text": text, "topic": topic}
