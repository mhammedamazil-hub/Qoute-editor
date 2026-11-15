"""FastAPI application: REST + WebSocket + static dashboard serving."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..brain import get_brain
from .routes import build_router
from .ws import hub, telemetry_loop


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(telemetry_loop(brain, interval=1.5))
        yield
        task.cancel()

    app = FastAPI(title="MiniCoder Brain API", version="0.1.0",
                  description="Cognitive core: memory, sleep, skills, shards — offline-first.",
                  lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # local-first tool; binds to localhost by default
        allow_methods=["*"],
        allow_headers=["*"],
    )
    brain = get_brain()
    app.include_router(build_router(brain), prefix="/api/brain")

    @app.websocket("/ws/telemetry")
    async def telemetry(ws: WebSocket) -> None:
        await hub.connect(ws)
        try:
            await ws.send_text(__import__("json").dumps({"type": "status", **brain.status()}, default=str))
            while True:
                # clients may send {"type":"ping"}; we just keep the socket warm & broadcast
                await ws.receive_text()
        except WebSocketDisconnect:
            hub.disconnect(ws)
        except Exception:
            hub.disconnect(ws)

    # Serve the built single-file dashboard if it exists (npm run build → dist/index.html)
    dist = Path(__file__).resolve().parent.parent.parent.parent / "dist"
    if dist.exists() and (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="dashboard")
    return app


app = create_app()
