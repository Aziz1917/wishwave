import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket


class RealtimeManager:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, room_key: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms[room_key].add(websocket)

    async def disconnect(self, room_key: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._rooms.get(room_key)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._rooms.pop(room_key, None)

    async def broadcast(self, room_key: str, payload: dict) -> None:
        async with self._lock:
            sockets = list(self._rooms.get(room_key, set()))

        if not sockets:
            return

        message = json.dumps(payload, ensure_ascii=False)
        dead_sockets: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_text(message)
            except Exception:
                dead_sockets.append(socket)

        if dead_sockets:
            async with self._lock:
                for socket in dead_sockets:
                    self._rooms.get(room_key, set()).discard(socket)


realtime_manager = RealtimeManager()

