from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[job_id].add(websocket)

    def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        self.connections[job_id].discard(websocket)
        if not self.connections[job_id]:
            self.connections.pop(job_id, None)

    async def broadcast(self, job_id: str, payload: Dict[str, Any]) -> None:
        stale: List[WebSocket] = []
        for websocket in tuple(self.connections.get(job_id, ())):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(job_id, websocket)

    def broadcast_from_thread(self, job_id: str, payload: Dict[str, Any]) -> None:
        if self.loop is not None and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(job_id, payload), self.loop)


manager = ConnectionManager()
