"""
SyriaBot - WebSocket Manager
============================

Real-time server stats broadcasting.

Author: حَـــــنَّـــــا
"""

import asyncio
import json
from typing import Set, Dict, Any, Optional

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from src.core.logger import logger


class WebSocketManager:
    """Manages WebSocket connections and real-time stats broadcasting."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

        # Current stats
        self._stats: Dict[str, int] = {
            "members": 0,
            "online": 0,
            "boosts": 0,
            "messages": 0,
            "ranked": 0,
            "xp": 0,
            "voice_minutes": 0,
        }

        # Background task for periodic online count updates
        self._online_task: Optional[asyncio.Task] = None
        self._bot = None

    def set_bot(self, bot) -> None:
        """Set bot reference for online count updates."""
        self._bot = bot

    async def start_online_updates(self) -> None:
        """Start periodic online count updates (every 30 seconds)."""
        if self._online_task is not None:
            return

        self._online_task = asyncio.create_task(self._online_update_loop())
        logger.tree("WebSocket Online Updates", [
            ("Interval", "30 seconds"),
        ], emoji="🟢")

    async def stop_online_updates(self) -> None:
        """Stop periodic online count updates."""
        if self._online_task:
            self._online_task.cancel()
            try:
                await self._online_task
            except asyncio.CancelledError:
                pass
            self._online_task = None

    async def _online_update_loop(self) -> None:
        """Background task to update online count and XP stats every 30 seconds."""
        from src.core.config import config
        from src.services.database import db

        while True:
            try:
                await asyncio.sleep(30)

                if not self._bot or not self._bot.is_ready():
                    continue

                guild = self._bot.get_guild(config.GUILD_ID)
                if not guild:
                    continue

                updates: Dict[str, int] = {}

                # Count online members (not offline, not bots)
                online = sum(
                    1 for m in guild.members
                    if not m.bot and m.status.name != "offline"
                )
                if online != self._stats["online"]:
                    updates["online"] = online

                # Update XP stats (ranked users and total XP)
                try:
                    xp_stats = db.get_xp_stats(config.GUILD_ID)
                    ranked = xp_stats.get("total_users", 0)
                    total_xp = xp_stats.get("total_xp", 0)

                    if ranked != self._stats["ranked"]:
                        updates["ranked"] = ranked
                    if total_xp != self._stats["xp"]:
                        updates["xp"] = total_xp
                except Exception:
                    pass  # Don't fail online updates if XP stats fail

                # Broadcast all changes at once
                if updates:
                    await self.broadcast_stats(updates)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error_tree("Stats Update Error", e)
                await asyncio.sleep(30)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a new connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

        # Send current stats immediately
        await self._send_full_stats(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a connection."""
        async with self._lock:
            self._connections.discard(websocket)

    async def _send_full_stats(self, websocket: WebSocket) -> None:
        """Send all current stats to a single client."""
        try:
            message = json.dumps({
                "type": "stats",
                "data": self._stats.copy()
            })
            await websocket.send_text(message)
        except Exception:
            pass

    def set_stats(
        self,
        members: int,
        online: int,
        boosts: int,
        messages: int,
        ranked: int = 0,
        xp: int = 0,
        voice_minutes: int = 0
    ) -> None:
        """Set all stats at once (used during initialization)."""
        self._stats["members"] = members
        self._stats["online"] = online
        self._stats["boosts"] = boosts
        self._stats["messages"] = messages
        self._stats["ranked"] = ranked
        self._stats["xp"] = xp
        self._stats["voice_minutes"] = voice_minutes

    def set_stat(self, key: str, value: int) -> None:
        """Set a single stat without broadcasting."""
        if key in self._stats:
            self._stats[key] = value

    async def broadcast_stat(self, key: str, value: int) -> None:
        """Broadcast a single stat update to all clients."""
        if key not in self._stats:
            return

        self._stats[key] = value

        if not self._connections:
            return

        message = json.dumps({
            "type": "stat_update",
            "data": {key: value}
        })

        await self._broadcast(message)

    async def broadcast_stats(self, updates: Dict[str, int]) -> None:
        """Broadcast multiple stat updates at once."""
        for key, value in updates.items():
            if key in self._stats:
                self._stats[key] = value

        if not self._connections:
            return

        message = json.dumps({
            "type": "stat_update",
            "data": updates
        })

        await self._broadcast(message)

    async def _broadcast(self, message: str) -> None:
        """Broadcast a message to all connected clients."""
        dead_connections = set()

        async with self._lock:
            for websocket in self._connections:
                try:
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.send_text(message)
                except Exception:
                    dead_connections.add(websocket)

            self._connections -= dead_connections

    # Increment methods for real-time updates (no DB query needed)
    async def increment_xp(self, amount: int) -> None:
        """Increment total XP counter and broadcast."""
        self._stats["xp"] += amount
        if self._connections:
            await self.broadcast_stat("xp", self._stats["xp"])

    async def increment_ranked(self) -> None:
        """Increment ranked users counter and broadcast."""
        self._stats["ranked"] += 1
        if self._connections:
            await self.broadcast_stat("ranked", self._stats["ranked"])

    async def increment_voice_minutes(self, amount: int = 1) -> None:
        """Increment voice minutes counter and broadcast."""
        self._stats["voice_minutes"] += amount
        if self._connections:
            await self.broadcast_stat("voice_minutes", self._stats["voice_minutes"])

    # Legacy methods for backwards compatibility
    def set_message_count(self, count: int) -> None:
        """Set message count (legacy method)."""
        self._stats["messages"] = count

    async def broadcast_message_count(self, count: int) -> None:
        """Broadcast message count (legacy method)."""
        await self.broadcast_stat("messages", count)

    @property
    def message_count(self) -> int:
        """Get current message count."""
        return self._stats["messages"]

    @property
    def stats(self) -> Dict[str, int]:
        """Get all current stats."""
        return self._stats.copy()

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
