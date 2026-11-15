"""REST surface for the brain. All under /api/brain."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import episodic, semantic, procedural
from ..db import counts
from ..snapshot import export_snapshot, import_snapshot
from ..sleep import latest_sleep_report
from ..visual import ingest_image


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class RememberIn(BaseModel):
    situation: str = Field(min_length=1, max_length=4000)
    modality: str = "text"
    objective: str = ""
    result: str = ""
    source: str = "user_instruction"
    confidence: float = 0.6
    tags: list[str] = []
    verification_status: str = "UNVERIFIED"


class VerifyCodeIn(BaseModel):
    task: str = Field(min_length=1)
    solution: str = Field(min_length=1)
    tests: str = Field(min_length=1)
    domain: str = "python"
    skill_name: str | None = None


class SleepIn(BaseModel):
    trigger: str = "user_requested"


class SnapshotImportIn(BaseModel):
    path: str


class ImageIngestIn(BaseModel):
    path: str
    description: str = ""
    tags: list[str] = []


def build_router(brain) -> APIRouter:
    r = APIRouter()

    @r.get("/status")
    def status():
        return brain.status()

    @r.post("/chat")
    def chat(body: ChatIn):
        try:
            return brain.chat(body.message)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @r.get("/memory/stats")
    def memory_stats():
        return counts()

    @r.get("/memory/episodes")
    def episodes(limit: int = Query(20, ge=1, le=200), status: str | None = None,
                 archived: bool = False):
        return [e.model_dump(mode="json") for e in
                episodic.list_episodes(limit=limit, status=status, include_archived=archived)]

    @r.get("/memory/search")
    def search(q: str = Query(min_length=1), top_k: int = Query(6, ge=1, le=20)):
        return [{"score": s, "episode": e.model_dump(mode="json")}
                for e, s in episodic.search_episodes(q, top_k=top_k)]

    @r.post("/memory/remember")
    def remember(body: RememberIn):
        ep = episodic.record_episode(
            situation=body.situation, modality=body.modality, objective=body.objective,
            result=body.result, source=body.source, confidence=body.confidence,
            tags=body.tags, verification_status=body.verification_status)
        return ep.model_dump(mode="json")

    @r.get("/skills")
    def skills(status: str | None = None, domain: str | None = None):
        return [s.model_dump(mode="json") for s in procedural.list_skills(status=status, domain=domain)]

    @r.post("/skills/verify-code")
    def verify_code(body: VerifyCodeIn):
        return brain.run_coding_task(task=body.task, solution=body.solution,
                                     tests=body.tests, domain=body.domain,
                                     skill_name=body.skill_name)

    @r.get("/graph")
    def graph(limit: int = Query(150, ge=10, le=500)):
        return semantic.graph_payload(limit=limit)

    @r.get("/graph/neighbourhood")
    def neighbourhood(label: str = Query(min_length=1), depth: int = Query(2, ge=1, le=3)):
        return semantic.neighbourhood(label, depth=depth)

    @r.post("/sleep")
    def sleep(body: SleepIn):
        return brain.sleep(trigger=body.trigger)

    @r.get("/sleep/report")
    def sleep_report():
        report = latest_sleep_report()
        if report is None:
            raise HTTPException(404, "no sleep has run yet")
        return report

    @r.post("/snapshot/export")
    def snapshot_export():
        path = export_snapshot()
        return {"path": str(path), "size_bytes": path.stat().st_size}

    @r.post("/snapshot/import")
    def snapshot_import(body: SnapshotImportIn):
        try:
            return import_snapshot(Path(body.path))
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(400, str(e))

    @r.post("/visual/ingest")
    def visual_ingest(body: ImageIngestIn):
        try:
            return ingest_image(body.path, description=body.description, tags=body.tags)
        except FileNotFoundError:
            raise HTTPException(404, f"no such image: {body.path}")

    @r.get("/doctor")
    def doctor():
        from ..brain import hardware_profile
        from ..llm import provider_status
        from ..db import init_db
        db = init_db()
        return {"db": str(db), "db_exists": db.exists(),
                "counts": counts(), "provider": provider_status(),
                "hardware": hardware_profile()}

    return r
