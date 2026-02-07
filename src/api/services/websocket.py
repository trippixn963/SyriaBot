"""
SyriaBot - WebSocket Manager
============================

Real-time message count broadcasting.

Author: حَـــــنَّـــــا
"""

import asyncio
import json
from typing import Set

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from src.core.logger import logger


class WebSocketManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._message_count: int = 0

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a new connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.debug(f"WebSocket connected. Total: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a connection."""
        async with self._lock:
            self._connections.discard(websocket)
        logger.debug(f"WebSocket disconnected. Total: {len(self._connections)}")

    def set_message_count(self, count: int) -> None:
        """Set the current message count."""
        self._message_count = count

    async def broadcast_message_count(self, count: int) -> None:
        """Broadcast updated message count to all clients."""
        self._message_count = count

        if not self._connections:
            return

        message = json.dumps({
            "type": "message_count",
            "data": {"total_messages": count}
        })

        dead_connections = set()

        async with self._lock:
            for websocket in self._connections:
                try:
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.send_text(message)
                except Exception:
                    dead_connections.add(websocket)

            self._connections -= dead_connections

    @property
    def message_count(self) -> int:
        """Get current message count."""
        return self._message_count

    @property
    def connection_count(self) -> int:
        """Get current connection count."""
        return len(self._connections)


# Singleton
_ws_manager: WebSocketManager | None = None


def get_ws_manager() -> WebSocketManager:
    """Get WebSocket manager singleton."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager


__all__ = ["WebSocketManager", "get_ws_manager"]
