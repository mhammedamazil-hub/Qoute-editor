"""FastAPI backend: chat, editor actions, vision, memory, sleep, telemetry.

The server owns one ``BrainService`` (a single runtime with the memory systems,
the neural models and the editor bridge) and exposes it over REST + WebSocket.
All state shown in the dashboard comes from this API — nothing is mocked.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from minicoder.config import CONFIG
from minicoder.memory.db import BrainDB

# --------------------------------------------------------------------------
# request/response models (Pydantic v2, strict where it matters)
# --------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = "default"
    allow_actions: bool = True
    # Explicit grant for consequential actions (delete, export, push, reset…). Without it
    # such a request is refused with the reason, never executed "helpfully".
    authorize: bool = False


class ChatResponse(BaseModel):
    answer: str
    source: str
    confidence: float
    grounding: list[dict[str, Any]] = []
    route: str = ""
    steps: list[dict[str, Any]] = []
    verified: bool = False
    elapsed_ms: float = 0.0
    intent: dict[str, Any] = {}


class CanvasRequest(BaseModel):
    width: int = Field(ge=64, le=8000, default=1080)
    height: int = Field(ge=64, le=8000, default=1350)


class ToolRequest(BaseModel):
    tool: str
    args: dict[str, Any] = {}


class SleepRequest(BaseModel):
    trigger: str = "api"
    push: bool = False
    train: bool = False


class MemoryWrite(BaseModel):
    kind: str = "fact"
    label: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=1, max_length=8000)
    source: str = "user_instruction"
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


# --------------------------------------------------------------------------
# the runtime
# --------------------------------------------------------------------------


class BrainService:
    """Single-process runtime shared by every endpoint."""

    def __init__(self) -> None:
        from minicoder.cognition.agent import DesignAgent
        from minicoder.cognition.engine import NeuralBrain
        from minicoder.memory.systems import (
            EpisodicMemory,
            ProceduralMemory,
            SemanticMemory,
            VisualMemory,
            WorkingMemory,
        )

        self.db = BrainDB()
        self.episodic = EpisodicMemory(self.db)
        self.semantic = SemanticMemory(self.db)
        self.procedural = ProceduralMemory(self.db)
        self.visual = VisualMemory(self.db)
        self.working = WorkingMemory()
        self.brain = NeuralBrain()
        self.agent = DesignAgent(self.db, brain=self.brain)
        self.state = "WAKE"
        self.events: list[dict[str, Any]] = []
        self.subscribers: set[WebSocket] = set()
        self.sleep_engine = None
        self.session_turns: dict[str, list[dict[str, str]]] = {}
        self.started_at = time.time()

    # ------------------------------------------------------------ telemetry
    def emit(self, state: str, event: str, data: dict[str, Any] | None = None) -> None:
        if state:
            self.state = state
        payload = {"ts": time.time(), "state": self.state, "event": event, "data": data or {}}
        self.events.append(payload)
        self.events = self.events[-500:]
        self.db.telemetry(self.state, event, data or {})
        for ws in list(self.subscribers):
            try:
                asyncio.get_event_loop().create_task(
                    ws.send_text(json.dumps(payload, default=str))
                )
            except Exception:
                self.subscribers.discard(ws)

    # --------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:

        mc = self.agent.mc
        return {
            "state": self.state,
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "brain": self.brain.info(),
            "memory": {
                **self.db.stats(),
                "working": self.working.stats(),
                "semantic_graph": self.semantic.stats(),
                "procedural": self.procedural.stats(),
                "visual": self.visual.stats(),
            },
            "calibration": mc.calibration(),
            "sleep": {
                "busy": bool(self.sleep_engine and self.sleep_engine.busy),
                "cycles": self.db.query_one("SELECT COUNT(*) FROM sleep_cycles")[0],
            },
            "editor": {"online": self._editor_online()},
            "embedder": _embedder_backend(),
            "paths": {
                "home": str(CONFIG.paths.home),
                "brain_db": str(CONFIG.paths.brain_db),
            },
            "events": self.events[-30:],
        }

    def _editor_online(self) -> bool:
        try:
            self.agent.bridge._ensure()
            return True
        except Exception:
            return False


def _embedder_backend() -> str:
    try:
        from minicoder.model.embeddings import backend

        return backend()
    except Exception:
        return "unknown"


SERVICE: BrainService | None = None


def service() -> BrainService:
    global SERVICE
    if SERVICE is None:
        SERVICE = BrainService()
    return SERVICE


# --------------------------------------------------------------------------
# app
# --------------------------------------------------------------------------

app = FastAPI(
    title="Project MiniCoder",
    description="A compact, multimodal, self-evolving cognitive brain.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CONFIG.api.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    svc = service()
    db_ok = svc.db.verify_integrity()
    return {"ok": db_ok["ok"], "db": db_ok["detail"], "state": svc.state}


@app.get("/api/status")
def status() -> dict[str, Any]:
    return service().status()


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    svc = service()
    t0 = time.time()
    svc.emit("THINK", "chat_start", {"chars": len(req.message)})
    turns = svc.session_turns.setdefault(req.session_id, [])
    svc.working.put("message", req.message, priority=0.95)

    if req.allow_actions:
        traj = svc.agent.execute(req.message, authorize=req.authorize)
        answer = traj.summary
        if traj.steps:
            source = "skill" if traj.verified else "tool"
        else:
            # The agent may simply have answered instead of acting. Report the
            # answerer's real provenance: labelling a refusal "memory" claimed
            # evidence that did not exist.
            source = traj.source or ("memory" if traj.verified else "refuse")
        grounding = [{"type": "plan", "steps": traj.plan}]
        steps = [s.to_json() for s in traj.steps]
        verified = traj.verified
        confidence = traj.confidence
    else:
        gen = svc.agent.answerer.answer(req.message)
        answer, source, grounding = gen.text, gen.source, gen.grounding
        steps, verified, confidence = [], gen.source in ("skill", "memory"), 0.5

    intent = getattr(traj, "intent", {}) if req.allow_actions else {}
    if intent.get("requires_authorization"):
        svc.db.log_provenance(
            "chat", None, "authorization",
            detail={"granted": bool(req.authorize), "intent": intent.get("type"),
                    "actions": intent.get("consequential", [])[:3]})

    turns.append({"user": req.message, "assistant": answer[:2000]})
    svc.emit("REMEMBER", "chat_done", {"source": source, "verified": verified})
    return ChatResponse(
        answer=answer,
        source=source,
        confidence=round(float(confidence), 3),
        grounding=grounding,
        route=source,
        steps=steps,
        verified=verified,
        elapsed_ms=round((time.time() - t0) * 1000, 1),
        intent=intent,
    )


@app.post("/api/editor/canvas")
def set_canvas(req: CanvasRequest) -> dict[str, Any]:
    svc = service()
    traj = svc.agent.execute(f"Set the canvas to {req.width}x{req.height}")
    return {"ok": traj.verified, "summary": traj.summary, "steps": [s.to_json() for s in traj.steps]}


@app.post("/api/editor/tool")
def call_tool(req: ToolRequest) -> dict[str, Any]:
    """Raw tool passthrough with the same verification gate as the agent."""
    from minicoder.tools.editor_bridge import verify_tool_outcome

    svc = service()
    svc.emit("ACT", "tool_call", {"tool": req.tool})
    try:
        before = svc.agent.bridge.state()
        result, after = svc.agent.bridge.call(req.tool, req.args)
        ok, checks = verify_tool_outcome(req.tool, req.args, result, before, after)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"editor bridge: {exc}") from exc
    return {"ok": ok, "result": result, "checks": checks}


@app.get("/api/editor/tools")
def list_tools() -> dict[str, Any]:
    try:
        return {"tools": service().agent.bridge.list_tools()}
    except Exception as exc:
        return {"tools": [], "error": str(exc)}


@app.get("/api/editor/state")
def editor_state() -> dict[str, Any]:
    try:
        return service().agent.bridge.state()
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/vision/inspect")
async def inspect_image(file: UploadFile) -> dict[str, Any]:
    svc = service()
    svc.emit("PERCEIVE", "image_received", {"name": file.filename})
    from PIL import Image

    from minicoder.tools.vision import inspect as inspect_tool

    raw = await file.read()
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="image larger than 12 MB")
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"not a readable image: {exc}") from exc
    report = inspect_tool(img, save_to_memory=True, use_vision_model=True)
    svc.episodic.add(
        __import__("minicoder.memory.systems", fromlist=["Episode"]).Episode(
            situation=f"User uploaded an image ({img.width}x{img.height})",
            objective="Inspect the image and describe its UI state",
            modality="vision",
            actions=[{"tool": "vision.inspect", "labels": [report.ui_class]}],
            result=report.description,
            status="VERIFIED" if report.ui_class else "UNVERIFIED",
            source="visual_inspection",
            lessons=report.description[:200],
            confidence=report.ui_class_confidence or 0.4,
            surprise=0.5,
        )
    )
    svc.emit("REMEMBER", "image_stored", {"class": report.ui_class})
    payload = report.to_json()
    payload["_id"] = report.memory_id
    # Small inline preview so the inspector can render without a second round-trip.
    buf = io.BytesIO()
    thumb = img.copy()
    thumb.thumbnail((720, 720))
    thumb.save(buf, format="PNG")
    payload["_preview"] = base64.b64encode(buf.getvalue()).decode()
    return payload


@app.get("/api/vision")
def list_visual(limit: int = 30) -> dict[str, Any]:
    return {"items": service().visual.all(limit)}


@app.get("/api/vision/{vid}/image")
def visual_image(vid: int) -> FileResponse:
    row = service().visual.get(vid)
    if not row:
        raise HTTPException(status_code=404, detail="visual memory not found")
    path = CONFIG.paths.home / row["image_path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="image file missing")
    return FileResponse(path)


@app.get("/api/memory/search")
def memory_search(q: str, limit: int = 8) -> dict[str, Any]:
    svc = service()
    return {
        "semantic": svc.semantic.search(q, limit=limit),
        "episodes": svc.episodic.search(q, limit=limit),
        "visual": svc.visual.search(q, limit=limit),
         "skills": [
            s for s in svc.procedural.verified()
            if q.lower() in (s["name"] + s["description"]).lower()
        ][:limit],
    }


@app.post("/api/memory")
def memory_write(req: MemoryWrite) -> dict[str, Any]:
    svc = service()
    nid = svc.semantic.upsert(
        req.kind, req.label, req.content,
        status="UNVERIFIED", source=req.source, confidence=req.confidence,
    )
    return {"id": nid, "status": "UNVERIFIED"}


@app.get("/api/graph")
def graph() -> dict[str, Any]:
    return service().semantic.export_graph()


@app.get("/api/episodes")
def episodes(limit: int = 40, status: str | None = None) -> dict[str, Any]:
    svc = service()
    if status:
        rows = svc.db.query(
            "SELECT * FROM episodes WHERE status=? AND archived=0 ORDER BY id DESC LIMIT ?",
            (status, limit),
        )
        return {"items": [dict(r) for r in rows]}
    return {"items": svc.episodic.recent(limit)}


@app.get("/api/skills")
def skills(status: str | None = None) -> dict[str, Any]:
    svc = service()
    return {"items": svc.procedural.any(status), "stats": svc.procedural.stats()}


@app.post("/api/sleep")
def sleep(req: SleepRequest) -> dict[str, Any]:
    svc = service()
    if svc.sleep_engine and svc.sleep_engine.busy:
        raise HTTPException(status_code=409, detail="a sleep cycle is already running")
    from minicoder.sleep.engine import SleepEngine

    engine = SleepEngine(
        svc.db,
        on_stage=lambda name, payload: svc.emit(
            "SLEEP" if payload.get("status") == "start" else "COMPILE", f"sleep:{name}", payload
        ),
        push_to_github=req.push,
        train_after_compile=req.train,
    )
    svc.sleep_engine = engine
    svc.emit("SLEEP", "sleep_start", {"trigger": req.trigger})
    try:
        report = engine.sleep(trigger=req.trigger)
    except Exception as exc:
        svc.emit("WAKE", "sleep_failed", {"error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    svc.emit("WAKE", "sleep_done", {"cycle": report.cycle_id, "seconds": report.duration_seconds})
    return report.to_json()


@app.get("/api/sleep/reports")
def sleep_reports(limit: int = 10) -> dict[str, Any]:
    rows = service().db.query(
        "SELECT id, started_at, ended_at, trigger, status, report FROM sleep_cycles ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return {"items": [dict(r) for r in rows]}


@app.get("/api/sleep/latest")
def sleep_latest() -> HTMLResponse:
    path = CONFIG.paths.sleep_logs / "latest.md"
    if not path.exists():
        return HTMLResponse("<p>No sleep cycle has run yet.</p>")
    text = path.read_text(encoding="utf-8")
    escaped = (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return HTMLResponse(
        f"<html><body style='font-family:ui-monospace,monospace;background:#0b0c10;color:#e8e6e3;"
        f"padding:24px;white-space:pre-wrap;line-height:1.5'>{escaped}</body></html>"
    )


@app.get("/api/eval")
def eval_report() -> dict[str, Any]:
    path = CONFIG.paths.training_runs / "eval_report.json"
    if not path.exists():
        return {"available": False, "reason": "run `minicoder eval` first"}
    return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}


@app.get("/api/training")
def training_runs() -> dict[str, Any]:
    svc = service()
    rows = svc.db.query("SELECT * FROM training_runs ORDER BY id DESC LIMIT 20")
    shards = svc.db.query("SELECT * FROM dataset_shards ORDER BY id DESC LIMIT 20")
    runs: dict[str, Any] = {}
    for f in CONFIG.paths.training_runs.glob("*_metrics.json"):
        try:
            runs[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {
        "runs": [dict(r) for r in rows],
        "shards": [dict(r) for r in shards],
        "pipeline": runs,
        "checkpoints": sorted(p.name for p in CONFIG.paths.checkpoints.glob("*") if p.is_file()),
    }


# --------------------------------------------------------------- learning API

@app.get("/api/cognition/overview")
def cognition_overview() -> dict:
    """Phase 4: intent mix, calibration and audit, all from recorded rows.

    A missing measurement is reported as missing (``n`` is zero), never as a
    zero that reads like a passing score.
    """
    from minicoder.cognition.metacognition import Metacognition

    svc = service()
    semantic = svc.agent.semantic
    mc = Metacognition(svc.db)
    cal = mc.reliability()

    intents: dict[str, int] = {}
    for r in svc.db.query("SELECT intent FROM audit_log WHERE intent != ''"):
        intents[str(r["intent"])] = intents.get(str(r["intent"]), 0) + 1

    audits = []
    for r in svc.db.query(
            "SELECT ts, action, intent, authorized, allowed, detail FROM audit_log"
            " ORDER BY id DESC LIMIT 20"):
        audits.append({"ts": r["ts"], "action": r["action"], "intent": r["intent"],
                       "authorized": bool(r["authorized"]), "allowed": bool(r["allowed"]),
                       "detail": json.loads(r["detail"] or "{}")})

    refusals = sum(1 for a in audits if not a["allowed"])
    return {
        "calibration": cal,
        "calibration_history": [
            {"ts": r["ts"], "predicted": r["predicted"], "outcome": r["outcome"],
             "source": r["source"]}
            for r in svc.db.query("SELECT ts, predicted, outcome, source FROM calibration"
                                  " ORDER BY id DESC LIMIT 50")],
        "intent_counts": intents,
        "audit": audits,
        "refused_actions": refusals,
        "memory": {"episodes": svc.db.query_one(
            "SELECT COUNT(*) c FROM episodes")["c"],
            "semantic_nodes": svc.db.query_one(
                "SELECT COUNT(*) c FROM semantic_nodes WHERE archived = 0")["c"],
            "skills": svc.db.query_one(
                "SELECT COUNT(*) c FROM skills WHERE status='VERIFIED'")["c"]},
        "capabilities": semantic.stats() if semantic else {},
    }


@app.get("/api/generalization/overview")
def generalization_overview() -> dict:
    """Phase 4 generalization axes, read from the recorded report."""
    base = Path("datasets/research")
    path = base / "generalization_latest.json"
    if not path.exists():
        return {"available": False,
                "hint": "run `python -m minicoder.cli generalize` to produce a report"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"available": False, "error": "unreadable report"}
    data["available"] = True
    axes = []
    for name, row in (data.get("axes") or {}).items():
        if name == "overall":
            continue
        axes.append({"axis": name, **row})
    return {"available": True, "axes": axes,
            "overall": (data.get("axes") or {}).get("overall", {}),
            "leakage": data.get("leakage", {}),
            "fingerprint": data.get("fingerprint", ""),
            "seed": data.get("seed"), "seconds": data.get("seconds"),
            "results": data.get("results", [])}


@app.get("/api/sleep/adaptive")
def sleep_adaptive() -> dict:
    """The Adaptive Sleep 2.0 section of the last cycle, straight from its report."""
    svc = service()
    row = svc.db.query_one(
        "SELECT id, report FROM sleep_cycles WHERE status='ok' ORDER BY id DESC LIMIT 1")
    if not row or not row["report"]:
        return {"available": False}
    try:
        report = json.loads(row["report"])
    except json.JSONDecodeError:
        return {"available": False, "error": "unreadable cycle report"}
    return {"available": True, "cycle_id": row["id"],
            "adaptive": report.get("adaptive", {}),
            "fingerprint": report.get("fingerprint", ""),
            "stages": [{"stage": s.get("stage"), "name": s.get("name"),
                        "ms": s.get("ms")} for s in report.get("stages", [])]}


@app.get("/api/research/overview")
def research_overview() -> dict:
    """Phase 3 measurements, read from the recorded reports only.

    Nothing here is computed for display: every figure comes from
    datasets/research/*_latest.json, and a missing report is reported as missing rather
    than shown as a zero that looks like a measurement.
    """
    base = Path("datasets/research")

    def load(name: str):
        path = base / f"{name}_latest.json"
        if not path.exists():
            return {"available": False}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"available": False, "error": "unreadable report"}
        data["available"] = True
        return data

    acquisition = load("acquisition")
    transfer = load("transfer")
    retention = load("retention")
    meta = load("meta")
    security = load("security")

    arms = []
    if acquisition.get("available"):
        for arm, data in acquisition.get("arms", {}).items():
            ci = acquisition.get("rate_ci", {}).get(arm, {})
            arms.append({
                "arm": arm,
                "tasks": data.get("tasks", 0),
                "hidden_pass": data.get("hidden_pass", 0),
                "rate": data.get("hidden_pass_rate", 0),
                "ci_low": ci.get("lo"), "ci_high": ci.get("hi"),
                "established": bool(ci.get("established")),
                "dev_pass": data.get("dev_pass", 0),
                "test_fitted": data.get("test_fitted", 0),
                "mean_candidates": data.get("mean_candidates", 0),
            })

    escapes = 0
    probes = 0
    if security.get("available"):
        for rows in security.get("probes", {}).values():
            probes += len(rows)
            escapes += sum(1 for r in rows if r.get("escaped"))

    return {
        "acquisition": {
            "available": acquisition.get("available", False),
            "experiment_id": acquisition.get("experiment_id"),
            "commit": acquisition.get("git_commit"),
            "generated_at": acquisition.get("generated_at"),
            "seeds": acquisition.get("config", {}).get("seeds", []),
            "tasks_per_seed": acquisition.get("config", {}).get("n_tasks"),
            "generator": acquisition.get("generator_version"),
            "production_unchanged": acquisition.get("production_memory", {}).get("unchanged"),
            "arms": arms,
        },
        "transfer": {"available": transfer.get("available", False),
                     "summary": transfer.get("summary", {}),
                     "families": transfer.get("families", 0)},
        "retention": {"available": retention.get("available", False),
                      "retained": retention.get("retained", 0),
                      "families": retention.get("families", 0),
                      "verified": retention.get("verified_at_acquisition", 0),
                      "verified_retained": retention.get("verified_retained", 0)},
        "meta": {"available": meta.get("available", False),
                 "cost_reduction": meta.get("cost_reduction_from_reuse"),
                 "arm_c": meta.get("mean_candidates_arm_C"),
                 "arm_e": meta.get("mean_candidates_arm_E"),
                 "first": meta.get("first_occurrence_candidates"),
                 "later": meta.get("later_occurrence_candidates")},
        "security": {"available": security.get("available", False),
                     "probes": probes, "escapes": escapes,
                     "modes": [m.get("name") for m in security.get("modes", [])]},
    }

@app.get("/api/learning/overview")
def learning_overview() -> dict[str, Any]:
    """Everything the learning dashboard shows, from recorded measurements."""
    svc = service()
    db = svc.db

    def scalar(sql: str, params: tuple = ()) -> Any:
        try:
            row = db.query_one(sql, params)
            return row[0] if row else 0
        except Exception:
            return 0

    def rows(sql: str, params: tuple = (), limit: int = 50) -> list[dict[str, Any]]:
        try:
            return [dict(r) for r in db.query(sql + " LIMIT ?", (*params, limit))]
        except Exception:
            return []

    experiments = rows(
        "SELECT id, ts, task_key, title, domain, status, seconds, best_candidate_id"
        " FROM experiments ORDER BY id DESC", (), 30
    )
    attempts = rows(
        "SELECT n, ok, failure_class, duration_ms FROM attempts"
        " WHERE experiment_id=(SELECT MAX(id) FROM experiments) ORDER BY n", (), 50
    )
    candidates = rows(
        "SELECT c.id, c.slug, c.status, c.replay_passed, c.replay_runs,"
        " c.replay_failures, e.task_key FROM skill_candidates c"
        " LEFT JOIN experiments e ON e.id = c.experiment_id ORDER BY c.id DESC", (), 30
    )
    replays = rows(
        "SELECT skill_slug, task_key, variation, passed, ts FROM skill_replays"
        " ORDER BY id DESC", (), 40
    )
    resources = rows(
        "SELECT ts, rss_mb, cpu_seconds, context FROM resource_samples"
        " ORDER BY id DESC", (), 40
    )

    by_failure: dict[str, int] = {}
    for a in attempts:
        by_failure[a["failure_class"]] = by_failure.get(a["failure_class"], 0) + 1

    retention = _retention_series(db)

    return {
        "counts": {
            "experiments": scalar("SELECT COUNT(*) FROM experiments"),
            "solved": scalar("SELECT COUNT(*) FROM experiments WHERE status='solved'"),
            "exhausted": scalar("SELECT COUNT(*) FROM experiments WHERE status='exhausted'"),
            "hypotheses": scalar("SELECT COUNT(*) FROM hypotheses"),
            "attempts": scalar("SELECT COUNT(*) FROM attempts"),
            "failed_attempts": scalar("SELECT COUNT(*) FROM attempts WHERE ok=0"),
            "candidates": scalar("SELECT COUNT(*) FROM skill_candidates"),
            "awaiting_verification": scalar(
                "SELECT COUNT(*) FROM skill_candidates WHERE status='candidate'"),
            # The flag, not the status: a promoted candidate has already left the
        # 'replay_passed' status, so counting status showed 0 next to promoted=1.
        "replay_passed": scalar(
                "SELECT COUNT(*) FROM skill_candidates WHERE replay_passed=1"),
            "promoted": scalar(
                "SELECT COUNT(*) FROM skill_candidates WHERE status='promoted'"),
            "rejected": scalar(
                "SELECT COUNT(*) FROM skill_candidates WHERE status='rejected'"),
            "dependencies": scalar("SELECT COUNT(*) FROM skill_dependencies"),
        },
        "experiments": experiments,
        "attempts": attempts,
        "candidates": candidates,
        "replays": replays,
        "resources": resources,
        "failure_classes": dict(sorted(by_failure.items())),
        "retention": retention,
        "benchmark": _benchmark_summary(),
        "acceptance": _acceptance_summary(),
        "checkpoints": sorted(
            p.name for p in CONFIG.paths.checkpoints.glob("*") if p.is_file()),
        "baselines": sorted(
            p.name for p in (CONFIG.paths.home / "memory" / "baselines").glob("*")
            if p.is_dir()) if (CONFIG.paths.home / "memory" / "baselines").exists() else [],
    }


def _has_table(db: Any, name: str) -> bool:
    try:
        return db.query_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ) is not None
    except Exception:
        return False


def _retention_series(db: Any) -> list[dict[str, Any]]:
    """Pass rate per skill over time — the forgetting curve."""
    try:
        rows = db.query(
            "SELECT skill_slug, ts, passed FROM skill_replays ORDER BY id"
        )
    except Exception:
        return []
    series: dict[str, dict[str, Any]] = {}
    for r in rows:
        slug = r["skill_slug"]
        entry = series.setdefault(slug, {"slug": slug, "runs": 0, "passed": 0,
                                         "points": []})
        entry["runs"] += 1
        entry["passed"] += int(r["passed"])
        entry["points"].append({"ts": r["ts"], "passed": int(r["passed"])})
    for entry in series.values():
        entry["rate"] = round(entry["passed"] / entry["runs"], 3) if entry["runs"] else 0.0
        entry["points"] = entry["points"][-20:]
    return sorted(series.values(), key=lambda e: -e["runs"])


def _benchmark_summary() -> dict[str, Any]:
    path = CONFIG.paths.home.parent / "datasets" / "learning" / "benchmark_latest.json"
    if not path.exists():
        path = Path("datasets/learning/benchmark_latest.json")
    if not path.exists():
        return {"available": False, "reason": "run `minicoder benchmark` first"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"available": False, "reason": "unreadable report"}
    return {
        "available": True,
        "generated_at": data.get("generated_at"),
        "summary": data.get("summary", {}),
        "by_category": data.get("by_category", {}),
        "failed": data.get("failed", []),
        "tasks": [
            {k: t.get(k) for k in ("key", "category", "mode", "first_attempt_ok",
                                   "final_ok", "attempts", "seconds", "tokens")}
            for t in data.get("tasks", [])
        ],
    }


def _acceptance_summary() -> dict[str, Any]:
    path = Path("datasets/learning/acceptance_latest.json")
    if not path.exists():
        return {"available": False, "reason": "run `minicoder acceptance` first"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"available": False, "reason": "unreadable report"}
    return {
        "available": True,
        "generated_at": data.get("generated_at"),
        "passed": data.get("passed"),
        "total": data.get("total"),
        "all_passed": data.get("all_passed"),
        "checks": [{"n": c.get("n"), "name": c.get("name"), "passed": c.get("passed"),
                    "detail": c.get("detail")} for c in data.get("checks", [])],
    }


@app.get("/api/learning/experiments")
def learning_experiments(limit: int = 50) -> dict[str, Any]:
    svc = service()
    rows = svc.db.query("SELECT * FROM experiments ORDER BY id DESC LIMIT ?", (limit,))
    out = []
    for r in rows:
        exp = dict(r)
        exp["success_criteria"] = json.loads(exp.get("success_criteria") or "[]")
        exp["attempts"] = [dict(a) for a in svc.db.query(
            "SELECT n, ok, failure_class, error, duration_ms, tokens_used FROM attempts"
            " WHERE experiment_id=? ORDER BY n", (exp["id"],))]
        out.append(exp)
    return {"experiments": out}


@app.get("/api/learning/skills")
def learning_skills() -> dict[str, Any]:
    """Procedural memory split by how far it has been verified."""
    svc = service()
    db = svc.db
    learned = [dict(r) for r in db.query(
        "SELECT c.id, c.slug, c.status, c.replay_passed, c.replay_runs,"
        " c.replay_failures, c.procedure, e.task_key, e.title"
        " FROM skill_candidates c LEFT JOIN experiments e ON e.id=c.experiment_id"
        " ORDER BY c.id DESC")]
    for item in learned:
        try:
            item["steps"] = len(json.loads(item.pop("procedure") or "[]"))
        except Exception:
            item["steps"] = 0
        item["replay_failures"] = json.loads(item.get("replay_failures") or "[]")
    seeded = [dict(r) for r in db.query(
        "SELECT slug, name, domain, status, source, confidence FROM skills"
        " ORDER BY updated_at DESC LIMIT 100")]
    deps = [dict(r) for r in db.query(
        "SELECT skill_slug, depends_on, kind FROM skill_dependencies ORDER BY id DESC"
        " LIMIT 200")]
    return {"learned": learned, "seeded": seeded, "dependencies": deps}


@app.get("/api/export/snapshot")
def export_snapshot() -> dict[str, Any]:
    svc = service()
    path = svc.db.backup(tag="api_export")
    return {"path": str(path), "bytes": path.stat().st_size}


@app.websocket("/ws/telemetry")
async def telemetry(ws: WebSocket) -> None:
    await ws.accept()
    svc = service()
    svc.subscribers.add(ws)
    try:
        await ws.send_text(json.dumps({"state": svc.state, "event": "connected",
                                       "data": svc.status()}, default=str))
        while True:
            # Client pings keep the socket alive; we push events as they happen.
            msg = await asyncio.wait_for(ws.receive_text(), timeout=30)
            if msg == "status":
                await ws.send_text(json.dumps({"state": svc.state, "event": "status",
                                               "data": svc.status()}, default=str))
    except (TimeoutError, WebSocketDisconnect):
        pass
    finally:
        svc.subscribers.discard(ws)


# --------------------------------------------------------------------------
# dashboard (static bundle, built by Vite or served raw in dev)
# --------------------------------------------------------------------------

DASHBOARD_DIR = CONFIG.paths.dashboard / "dist"


@app.get("/assets/{path:path}")
def dashboard_asset(path: str) -> FileResponse:
    """Serve the built dashboard bundle (hashed asset filenames)."""
    target = (DASHBOARD_DIR / "assets" / path).resolve()
    if not str(target).startswith(str((DASHBOARD_DIR / "assets").resolve())):
        raise HTTPException(status_code=403, detail="path traversal blocked")
    if not target.exists():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(target)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    index_file = DASHBOARD_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>MiniCoder API is running</h1>"
        "<p>The dashboard has not been built yet. Run "
        "<code>npm --prefix minicoder/dashboard install &amp;&amp; npm --prefix minicoder/dashboard run build</code>, "
        "or open <a href='/docs'>/docs</a> for the API.</p>"
    )


def run(host: str | None = None, port: int | None = None, reload: bool = False) -> None:
    import uvicorn

    uvicorn.run(
        "minicoder.api.app:app",
        host=host or CONFIG.api.host,
        port=port or CONFIG.api.port,
        reload=reload,
    )


if __name__ == "__main__":
    run()
