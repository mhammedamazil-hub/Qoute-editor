"""WebSocket telemetry hub — pushes live brain state to the dashboard."""
from __future__ import annotations
import asyncio
import json
from typing import Any
from fastapi import WebSocket


class TelemetryHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(json.dumps(payload, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)


hub = TelemetryHub()


async def telemetry_loop(brain, interval: float = 1.0) -> None:
    """Background task: push status snapshot every `interval` seconds."""
    while True:
        try:
            status = brain.status()
            await hub.broadcast({"type": "status", **status})
        except Exception:
            pass
        await asyncio.sleep(interval)
